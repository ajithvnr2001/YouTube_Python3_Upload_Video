#!/usr/bin/python

import httplib2
import os
import sys
from apiclient.discovery import build
from apiclient.errors import HttpError
from apiclient.http import MediaFileUpload
from oauth2client.client import flow_from_clientsecrets
from oauth2client.file import Storage
from oauth2client.tools import argparser, run_flow

os.chdir('/content')
CLIENT_SECRETS_FILE = "client_secrets.json"
YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

def get_authenticated_service(args):
    flow = flow_from_clientsecrets(CLIENT_SECRETS_FILE, scope=YOUTUBE_UPLOAD_SCOPE)
    storage = Storage("%s-oauth2.json" % sys.argv[0])
    credentials = storage.get()
    if credentials is None or credentials.invalid:
        credentials = run_flow(flow, storage, args)
    return build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION,
                 http=credentials.authorize(httplib2.Http()))

def upload_caption(youtube, video_id, language, track_name, file_path):
    try:
        print(f"Uploading caption: {track_name} ({language})...")
        caption_snippet = {
            'videoId': video_id,
            'language': language,
            'name': track_name,
            'isDraft': False
        }
        media_body = MediaFileUpload(file_path, mimetype='application/octet-stream', resumable=True)
        insert_request = youtube.captions().insert(
            part='snippet',
            body={'snippet': caption_snippet},
            media_body=media_body
        )
        response = insert_request.execute()
        print(f"✓ Caption uploaded successfully!")
        print(f"  Caption ID: {response['id']}")
        return True
    except HttpError as e:
        print(f"✗ Error: {e.content.decode('utf-8')}")
        return False

if __name__ == '__main__':
    argparser.add_argument("--video-id", required=True, help="Existing YouTube video ID")
    argparser.add_argument("--language", required=True, help="Language code (e.g., en, es, hi)")
    argparser.add_argument("--name", required=True, help="Caption track name")
    argparser.add_argument("--file", required=True, help="Caption file path")
    argparser.add_argument("--noauth_local_webserver", action='store_true')
    
    args = argparser.parse_args()
    
    if not os.path.exists(args.file):
        exit(f"Caption file not found: {args.file}")
    
    youtube = get_authenticated_service(args)
    upload_caption(youtube, args.video_id, args.language, args.name, args.file)
