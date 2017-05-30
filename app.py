import os
import sys
import json

import requests
from flask import Flask, request

app = Flask(__name__)


@app.route('/', methods=['GET'])
def verify():
    # when the endpoint is registered as a webhook, it must echo back
    # the 'hub.challenge' value it receives in the query arguments
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.challenge"):
        if not request.args.get("hub.verify_token") == os.environ["VERIFY_TOKEN"]:
            return "Verification token mismatch", 403
        return request.args["hub.challenge"], 200

    return "Hello world", 200


@app.route('/', methods=['POST'])
def webhook():

    # endpoint for processing incoming messaging events

    data = request.get_json()
    # log(data)

    if data["object"] == "page":
        for entry in data["entry"]:
            for messaging_event in entry["messaging"]:

                if messaging_event.get("message"):  # someone sent us a message

                    sender_id = messaging_event["sender"]["id"]        # the facebook ID of the person sending you the message
                    recipient_id = messaging_event["recipient"]["id"]  # the recipient's ID, which should be your page's facebook ID
                    message_text = messaging_event["message"]["text"]  # the message's text

                    parse_message(message_text, sender_id)

    return "OK", 200


def send_message(recipient_id, message_text):

    # log("sending message to {recipient}: {text}".format(recipient=recipient_id, text=message_text))

    params = {
        "access_token": os.environ["PAGE_ACCESS_TOKEN"]
    }
    headers = {
        "Content-Type": "application/json"
    }
    data = json.dumps({
        "recipient": {
            "id": recipient_id
        },
        "message": {
            "text": message_text
        }
    })
    r = requests.post("https://graph.facebook.com/v2.6/me/messages",
                      params=params,
                      headers=headers,
                      data=data)
    if r.status_code != 200:
        log(r.status_code)
        log(r.text)


def log(message):  # simple wrapper for logging to stdout on heroku
    print str(message)
    sys.stdout.flush()

def parse_message(msg, recipient_id):
    if msg.startswith('@help'):
        help_message(recipient_id)
    else:
        send_message(recipient_id, "I didn't quite get that, try again?")

def time_message(msg, recipient_id):
    try:
        time = msg[6:]
        minutes = int(time.split(':')[0])
        seconds = int(time.split(':')[1])
        time_string = "Stored time of %d minutes, %d seconds for [current date]" % (minutes, seconds)
        send_message(recipient_id, time_string)
    except Exception as e:
        send_message(recipient_id, "Had trouble parsing your time, try again?")

def score_message(recipient_id):
    send_message(recipient_id, "Under construction")

def help_message(recipient_id):
    help_string = '\'@time minutes:seconds\' to log score'
    help_string += ', \'@scores\' to see top scores for today'
    help_string += ', all scores logged at goo.gl/0Erhtu.'
    help_string += 'Send \'@help\' to see this message again'
    send_message(recipient_id, help_string)

if __name__ == '__main__':
    app.run(debug=True)
