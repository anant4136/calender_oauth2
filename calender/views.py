import os
import json
from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect
from rest_framework.views import APIView
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
    'openid'
]
REDIRECT_URL = 'http://127.0.0.1:8000/rest/v1/calendar/redirect'
API_SERVICE_NAME = 'calendar'
API_VERSION = 'v3'


class GoogleCalendarInitView(APIView):
    def post(self, request):

        # Assuming the client_secret.json file is sent in the request body as a file
        client_secret_file = request.FILES.get('client_secret_file', None)

        if not client_secret_file:
            return HttpResponse('client_secret_file is required', status=400)

        # Save the client_secret.json file temporarily
        temp_file_path = os.path.join(settings.BASE_DIR, 'client_secrets')
        with open(temp_file_path, 'wb') as f:
            for chunk in client_secret_file.chunks():
                f.write(chunk)

        # Load the client_secret.json file
        with open(temp_file_path) as f:
            client_secret_data = json.load(f)

        # Get the necessary client secret values
        client_id = client_secret_data.get('client_id', None)
        client_secret = client_secret_data.get('client_secret', None)

        if not client_id or not client_secret:
            os.remove(temp_file_path)
            return HttpResponse('Invalid client_secret_file', status=400)

        flow = Flow.from_client_secrets_file(
            temp_file_path,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URL
        )

        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true'
        )

        # Store the state and temporary file path in the session
        request.session['oauth_state'] = state
        request.session['temp_file_path'] = temp_file_path

        return HttpResponseRedirect(authorization_url)


class GoogleCalendarRedirectView(APIView):
    def get(self, request):
        # Retrieve the state and temporary file path from the session
        state = request.session.pop('oauth_state', None)
        temp_file_path = request.session.pop('temp_file_path', None)

        if not state or not temp_file_path:
            return HttpResponse('Missing session data', status=400)

        flow = Flow.from_client_secrets_file(
            temp_file_path,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URL,
            state=state
        )

        authorization_response = request.build_absolute_uri()
        flow.fetch_token(authorization_response=authorization_response)

        # Load the credentials
        credentials = flow.credentials

        # Use the credentials to build the Google Calendar service
        service = build(API_SERVICE_NAME, API_VERSION, credentials=credentials)

        try:
            # Get list of events from the user's calendar
            events_result = service.events().list(
                calendarId='primary').execute()
            events = events_result.get('items', [])
            return HttpResponse(events)
        except HttpError as e:
            return HttpResponse(f'Error retrieving events: {str(e)}', status=500)
        finally:
            # Clean up the temporary file
            os.remove(temp_file_path)
