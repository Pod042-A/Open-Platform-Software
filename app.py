import json
import io
import imageio.v3 as iio
from typing import Union
from PIL import Image
from flask import Flask, request, abort, jsonify

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    ImageMessageContent,
    StickerMessageContent,
    VideoMessageContent,
    LocationMessageContent
)
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    MessagingApiBlob,
    ReplyMessageRequest,
    TextMessage
)

import google.generativeai as gemini

config = None
with open('./config.json', mode='r', encoding='utf-8') as ifs:
    config = json.loads(ifs.read())

app = Flask(__name__)

webhook_handler = WebhookHandler(config['line']['channel_secret'])
line_config = Configuration(access_token=config['line']['channel_access_token'])

gemini.configure(api_key=config['gemini']['api_key'])
model = gemini.GenerativeModel(
    model_name=config['gemini']['model_name'],
    generation_config=config['gemini']['generation_config'],
    system_instruction="""
You are an AI assistant in a messaging app.

- When the user sends an image, briefly describe the image.
- When the user sends a video, briefly describe the video.
- When the user sends a message that begins with "[Sticker]", this indicates the emotional meaning of a sticker (e.g., "[Sticker] I'm sorry").
    - Do not describe or repeat the sticker.
    - Respond naturally, as if talking to a human.
- When the user sends a message that begins with "[Language]", this indicates the language use in conversation.
- Always reply in the same language as the user's last full sentence.
- If there is no text, default to English.
- Never use the [Sticker] format in your own responses.

Keep your replies conversational and under 100 words.
"""
)
language: Union[str, None] = None
session = model.start_chat(history=[])

@app.route('/')
def hello():
    return 'NodeHub', 200

@app.route('/line/callback', methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        webhook_handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return {}, 200

@app.route('/line/history', methods=['GET', 'DELETE'])
def history():
    try:
        if request.method == 'GET':
            return jsonify([
                {"role": h.role, "text": h.parts[0].text}
                for h in session.history
            ]), 200

        elif request.method == 'DELETE':
            session.history = []
            return jsonify({"status": "cleared"}), 200

    except (AttributeError, IndexError) as e:
        abort(400, description=str(e))

@webhook_handler.add(MessageEvent, message=TextMessageContent)
def text_message(event):
    global language
    with ApiClient(configuration=line_config) as client:
        line_api = MessagingApi(client)
        profile = line_api.get_profile(user_id=event.source.user_id)
        messages: list = []

        if profile.language != language:
            messages.append(f'[Language] { profile.language }')
            language = profile.language

        message_content: str = event.message.text
        messages.append(message_content)
        
        response = session.send_message(messages)
        
        line_api.reply_message_with_http_info(
            ReplyMessageRequest(
                replyToken=event.reply_token,
                messages=[TextMessage(text=response.text)]
            )
        )

    return

@webhook_handler.add(MessageEvent, message=ImageMessageContent)
def image_message(event):
    global language
    with ApiClient(configuration=line_config) as client:
        line_api = MessagingApi(client)
        profile = line_api.get_profile(user_id=event.source.user_id)
        messages: list = []

        if profile.language != language:
            messages.append(f'[Language] { profile.language }')
            language = profile.language

        line_api_blob = MessagingApiBlob(client)
        message_content = line_api_blob.get_message_content_preview(message_id=event.message.id)
        image = Image.open(io.BytesIO(message_content))
        messages.append(image)
        
        response = session.send_message(messages)
        
        line_api.reply_message_with_http_info(
            ReplyMessageRequest(
                replyToken=event.reply_token,
                messages=[TextMessage(text=response.text)]
            )
        )

    return

@webhook_handler.add(MessageEvent, message=StickerMessageContent)
def sticker_message(event):
    global language
    with ApiClient(configuration=line_config) as client:
        line_api = MessagingApi(client)
        profile = line_api.get_profile(user_id=event.source.user_id)
        messages: list = []

        if profile.language != language:
            messages.append(f'[Language] { profile.language }')
            language = profile.language

        message_content: list[str] = event.message.keywords
        messages.append(f'[Sticker] { message_content }')

        response = session.send_message(messages)
        
        line_api.reply_message_with_http_info(
            ReplyMessageRequest(
                replyToken=event.reply_token,
                messages=[TextMessage(text=response.text)]
            )
        )

    return

@webhook_handler.add(MessageEvent, message=VideoMessageContent)
def video_message(event):
    global language
    with ApiClient(configuration=line_config) as client:
        line_api = MessagingApi(client)
        profile = line_api.get_profile(user_id=event.source.user_id)
        messages: list = []

        if profile.language != language:
            messages.append(f'[Language] { profile.language }')
            language = profile.language

        line_api_blob = MessagingApiBlob(client)
        message_content = line_api_blob.get_message_content(message_id=event.message.id)
        reader = iio.imiter(io.BytesIO(message_content), plugin='pyav')
    
        frames: list = []
        frame_interval = 30
        max_frames = 120
        for idx, frame in enumerate(reader):
            if idx % frame_interval == 0:
                image = Image.fromarray(frame)
                frames.append(image)
            if len(frames) >= max_frames:
                break

        messages.extend(frames)
        
        response = session.send_message(messages)
        
        line_api.reply_message_with_http_info(
            ReplyMessageRequest(
                replyToken=event.reply_token,
                messages=[TextMessage(text=response.text)]
            )
        )

    return

@webhook_handler.add(MessageEvent, message=LocationMessageContent)
def location_message(event):
    global language
    with ApiClient(configuration=line_config) as client:
        line_api = MessagingApi(client)
        profile = line_api.get_profile(user_id=event.source.user_id)
        messages: list = []

        if profile.language != language:
            messages.append(f'[Language] { profile.language }')
            language = profile.language

        messages.extend([
            f'[Location Title] { event.message.title }',
            f'[Location Address] { event.message.address }',
            f'[Latitude] { event.message.latitude }',
            f'[Longitude] { event.message.longitude }'
        ])
        
        response = session.send_message(messages)
        
        line_api.reply_message_with_http_info(
            ReplyMessageRequest(
                replyToken=event.reply_token,
                messages=[TextMessage(text=response.text)]
            )
        )

    return

if __name__ == '__main__':
    app.run(host=config['server']['host'], port=config['server']['port'])