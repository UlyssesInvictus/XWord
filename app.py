import os
import sys
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials as SAC
import datetime

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
    log(data)

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
    elif msg.startswith('@time'):
        time_message(msg, recipient_id)
    elif msg.startswith('@mystats'):
        send_message(load_sheet(), mystats_message(recipient_id))
    elif msg.startswith('@stats'):
        send_message(load_sheet(), stats_message(recipient_id))
    else:
        send_message(recipient_id, "I didn't quite get that, try again?")

def time_message(msg, recipient_id):
    try:
        time = msg[6:]
        if time.isdigit():
            minutes = 0
            seconds = int(time)
        else:
            minutes = int(time.split(':')[0]) if len(time.split(':')[0]) > 0 else 0
            seconds = int(time.split(':')[1])
        sheet = load_sheet()
        store_time(sheet, get_name(recipient_id), minutes, seconds)
        current_date = current_xword_date()
        time_string = "Stored %d:%d for " % (minutes, seconds)
        time_string += current_date.strftime("%m/%d")
        time_string += "\n\n"
        time_string += stats_message(sheet, recipient_id)
        send_message(recipient_id, time_string)
    except Exception as e:
        log(e)
        send_message(recipient_id, "Had trouble parsing your time, try again?")

def store_time(sheet, name, minutes, seconds):
    # find the right row from date/time
    last_written_row = current_row(sheet)
    current_date = current_xword_date()
    sheet.update_cell(last_written_row, 1, current_date.strftime("%A %B %d, %Y"))
    # find right column
    names = sheet.row_values(1)
    if name not in names:
        last_written_col = 2
        while(len(names[last_written_col]) > 0):
            last_written_col += 1
        last_written_col += 1
        sheet.update_cell(1, last_written_col, name)
    else:
        last_written_col = names.index(name) + 1
    # input time
    sheet.update_cell(last_written_row, last_written_col, minutes * 60 + seconds)

def stats_message(sheet, recipient_id):
    row = current_row(sheet)
    scores = sheet.row_values(row)[2:]
    scores = [(int(s), 3 + i) for i, s in enumerate(scores) if len(s) > 0]
    scores.sort(key=lambda x: x[0])
    stats_string = "Today's stats:\n"
    for i, s in enumerate(scores[:3]):
        stats_string += "%d. " % (i + 1)
        stats_string += sheet.cell(1, s[1]).value
        stats_string += ": %d\n" % s[0]
    if len(scores) > 0:
        stats_string += "\nAverage: %.2fs" % (sum([s[0] for s in scores]) * 1.0 / len(scores))
    return stats_string

def mystats_message(sheet, recipient_id):
    send_message(recipient_id, "Under construction")

def help_message(recipient_id):
    help_string = '\'@time minutes:seconds\' to log score'
    help_string += ', \'@stats\' to see stats for today'
    help_string += ', all scores logged at goo.gl/0Erhtu.'
    help_string += ' Send \'@help\' to see this message again'
    send_message(recipient_id, help_string)

def get_credentials():
    scope = ['https://www.googleapis.com/auth/spreadsheets']
    with open('client_secret.json') as f:
        client_data = json.load(f)
    client_data["private_key"] = os.environ['GOOGLE_SERVICE_PRIVATE_KEY'].replace("\\n", "\n")
    credentials = SAC.from_json_keyfile_dict(client_data, scope)
    return credentials

def load_sheet():
    gc = gspread.authorize(get_credentials())
    return gc.open_by_key('1GV0PtCvpqJaIkSQc4G22MGnPllQoBAkg-i0BaN_jpro').sheet1

def get_name(recipient_id):
    url = "https://graph.facebook.com/v2.6/"
    url += str(recipient_id)
    url += "?fields=first_name,last_name&access_token="
    url += os.environ["PAGE_ACCESS_TOKEN"]
    r = requests.get(url)
    return r.json()['first_name'] + ' ' + r.json()['last_name'][0] + '.'

def current_xword_date():
    current_date = datetime.datetime.today()
    if current_date.hour >= 22:
        current_date += datetime.timedelta(days=1)
    return current_date

def current_row(sheet):
    dates = sheet.col_values(1)
    last_written_row = 1
    while(len(dates[last_written_row]) > 0):
        last_written_row += 1
    current_date = current_xword_date()
    date_string = current_date.strftime("%A %B %d, %Y")
    if dates[last_written_row - 1] != date_string:
        last_written_row += 1
    return last_written_row


if __name__ == '__main__':
    app.run(debug=True)
