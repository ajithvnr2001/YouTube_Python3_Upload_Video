#!/usr/bin/python

"""
YouTube Video Uploader with Multiple Caption Support
=====================================================
Upload videos to YouTube with support for multiple subtitle files in different languages.

Installation:
    pip install --upgrade google-api-python-client oauth2client httplib2

Requirements:
    - client_secrets.json (OAuth 2.0 credentials from Google Cloud Console)
    - ffmpeg (for video processing)
"""

import httplib2
import os
import random
import sys
import time

from apiclient.discovery import build
from apiclient.errors import HttpError
from apiclient.http import MediaFileUpload
from oauth2client.client import flow_from_clientsecrets
from oauth2client.file import Storage
from oauth2client.tools import argparser, run_flow

# Explicitly tell the underlying HTTP transport library not to retry, since
# we are handling retry logic ourselves.
httplib2.RETRIES = 1

# Maximum number of times to retry before giving up.
MAX_RETRIES = 10

# Always retry when these exceptions are raised.
RETRIABLE_EXCEPTIONS = (httplib2.HttpLib2Error, IOError)

# Always retry when an apiclient.errors.HttpError with one of these status
# codes is raised.
RETRIABLE_STATUS_CODES = [500, 502, 503, 504]

CLIENT_SECRETS_FILE = "client_secrets.json"

# Updated scope to include caption management
YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.force-ssl"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

MISSING_CLIENT_SECRETS_MESSAGE = """
WARNING: Please configure OAuth 2.0

To make this sample run you will need to populate the client_secrets.json file
found at:

   %s

with information from the API Console
https://console.cloud.google.com/

For more information about the client_secrets.json file format, please visit:
https://developers.google.com/api-client-library/python/guide/aaa_client_secrets
""" % os.path.abspath(os.path.join(os.path.dirname(__file__), CLIENT_SECRETS_FILE))

VALID_PRIVACY_STATUSES = ("public", "private", "unlisted")


def get_authenticated_service(args):
    """Authenticate and return YouTube API service object"""
    flow = flow_from_clientsecrets(CLIENT_SECRETS_FILE,
                                   scope=YOUTUBE_UPLOAD_SCOPE,
                                   message=MISSING_CLIENT_SECRETS_MESSAGE)

    storage = Storage("%s-oauth2.json" % sys.argv[0])
    credentials = storage.get()

    if credentials is None or credentials.invalid:
        credentials = run_flow(flow, storage, args)

    return build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION,
                 http=credentials.authorize(httplib2.Http()))


def initialize_upload(youtube, options):
    """Initialize video upload with metadata"""
    tags = None
    if options.keywords:
        tags = options.keywords.split(",")

    body = dict(
        snippet=dict(
            title=options.title,
            description=options.description,
            tags=tags,
            categoryId=options.category
        ),
        status=dict(
            privacyStatus=options.privacyStatus
        )
    )

    insert_request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=MediaFileUpload(options.file, chunksize=-1, resumable=True)
    )

    response = resumable_upload(insert_request)
    return response


def resumable_upload(insert_request):
    """Handle resumable upload with retry logic"""
    response = None
    error = None
    retry = 0
    while response is None:
        try:
            print("Uploading file...")
            status, response = insert_request.next_chunk()
            if response is not None:
                if 'id' in response:
                    print("Video id '%s' was successfully uploaded." %
                          response['id'])
                else:
                    exit("The upload failed with an unexpected response: %s" % response)
        except HttpError as e:
            if e.resp.status in RETRIABLE_STATUS_CODES:
                error = "A retriable HTTP error %d occurred:\n%s" % (e.resp.status, e.content)
            else:
                raise
        except RETRIABLE_EXCEPTIONS as e:
            error = "A retriable error occurred: %s" % e

        if error is not None:
            print(error)
            retry += 1
            if retry > MAX_RETRIES:
                exit("No longer attempting to retry.")

            max_sleep = 2 ** retry
            sleep_seconds = random.random() * max_sleep
            print("Sleeping %f seconds and then retrying..." % sleep_seconds)
            time.sleep(sleep_seconds)

    return response


def upload_caption(youtube, video_id, language, track_name, file_path):
    """
    Upload a single caption track to the video

    Args:
        youtube: Authenticated YouTube API service object
        video_id: YouTube video ID
        language: ISO 639-1 language code (e.g., 'en', 'es', 'hi')
        track_name: Display name for the caption track
        file_path: Path to the subtitle file (.srt, .sbv, etc.)

    Returns:
        True if successful, False otherwise
    """
    try:
        print(f"  Uploading caption: {track_name} ({language})...")

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
        print(f"  ✓ Caption '{response['snippet']['name']}' uploaded successfully.")
        print(f"    Caption ID: {response['id']}")
        return True

    except HttpError as e:
        print(f"  ✗ HTTP error {e.resp.status} while uploading caption:")
        print(f"    {e.content.decode('utf-8')}")
        return False
    except Exception as e:
        print(f"  ✗ Error uploading caption: {e}")
        return False


def parse_caption_argument(cap_arg):
    """
    Parse caption argument in format: language:filepath or language:name:filepath

    Examples:
        'en:captions.srt' -> ('en', 'en', 'captions.srt')
        'en:English:captions.srt' -> ('en', 'English', 'captions.srt')

    Returns:
        Tuple of (language_code, track_name, file_path) or None if invalid
    """
    parts = cap_arg.split(':', 2)

    if len(parts) == 2:
        # Format: language:filepath
        lang_code, file_path = parts
        track_name = lang_code.upper()  # Use language code as name
        return (lang_code, track_name, file_path)

    elif len(parts) == 3:
        # Format: language:name:filepath
        lang_code, track_name, file_path = parts
        return (lang_code, track_name, file_path)

    else:
        return None


def main():
    # Video upload arguments
    argparser.add_argument("--file", required=True, help="Video file to upload")
    argparser.add_argument("--title", help="Video title", default="Test Title")
    argparser.add_argument("--description", help="Video description", default="Test Description")
    argparser.add_argument("--category", default="22", help="Numeric video category")
    argparser.add_argument("--keywords", help="Video keywords, comma separated", default="")
    argparser.add_argument("--privacyStatus", choices=VALID_PRIVACY_STATUSES,
                           default=VALID_PRIVACY_STATUSES[0], help="Video privacy status.")

    # Caption arguments (supports multiple captions)
    argparser.add_argument('--captions', nargs='+', 
                          help='Caption files in format: lang:filepath or lang:name:filepath. '
                               'Example: en:english.srt es:Spanish:spanish.srt hi:hindi.srt')

    args = argparser.parse_args()

    # Validate video file
    if not os.path.exists(args.file):
        exit("Please specify a valid file using the --file= parameter.")

    # Authenticate
    youtube = get_authenticated_service(args)

    try:
        # Step 1: Upload the video
        print("="*80)
        print("STEP 1: Uploading Video")
        print("="*80)
        response = initialize_upload(youtube, args)

        video_id = response.get('id')
        if video_id is None:
            print("Could not get uploaded video ID.")
            sys.exit(1)

        print(f"\n✓ Video uploaded successfully!")
        print(f"  Video ID: {video_id}")
        print(f"  Video URL: https://www.youtube.com/watch?v={video_id}")

        # Step 2: Upload captions if specified
        if args.captions:
            print("\n" + "="*80)
            print("STEP 2: Uploading Captions")
            print("="*80)

            success_count = 0
            total_count = len(args.captions)

            for cap_arg in args.captions:
                parsed = parse_caption_argument(cap_arg)

                if parsed is None:
                    print(f"\n✗ Invalid caption format: '{cap_arg}'")
                    print("  Use format: language:filepath or language:name:filepath")
                    continue

                lang_code, track_name, file_path = parsed

                # Validate file exists
                if not os.path.exists(file_path):
                    print(f"\n✗ Caption file not found: {file_path}")
                    continue

                # Upload the caption
                print(f"\nProcessing caption {success_count + 1}/{total_count}:")
                if upload_caption(youtube, video_id, lang_code, track_name, file_path):
                    success_count += 1

            # Summary
            print("\n" + "="*80)
            print(f"Caption Upload Complete: {success_count}/{total_count} successful")
            print("="*80)
        else:
            print("\nNo captions specified. Skipping caption upload.")

        print("\n✓ All operations completed successfully!")

    except HttpError as e:
        print(f"\nAn HTTP error {e.resp.status} occurred:\n{e.content}")
        sys.exit(1)


if __name__ == '__main__':
    main()
