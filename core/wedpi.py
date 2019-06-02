#!/usr/bin/env python

import socket
import time
import unicodedata
import os

try:
    import queue
except ImportError:
    import Queue as queue
from sys import exit

try:
    import tweepy
except ImportError:
    exit("This script requires the tweepy module\nInstall with: sudo pip install tweepy")

import scrollphathd
from scrollphathd.fonts import font5x7
from subprocess import check_output

#
# TWITTER INIT
#

consumer_key = os.getenv('TWITTER_CONSUMER_KEY')
consumer_secret = os.getenv('TWITTER_CONSUMER_SECRET')
access_token = os.getenv('TWITTER_ACCESS_TOKEN')
access_token_secret = os.getenv('TWITTER_ACCESS_SECRET')

if consumer_key == '' or consumer_secret == '' or access_token == '' or access_token_secret == '':
    print("You need to configure your Twitter API keys! Edit this file for more information!")
    exit(0)

#
# PARAMS
#

HASHTAG_TO_TRACK = '#tuffwed'
DISPLAY_BRIGHTNESS = 0.2
BOOT_SCROLL_DELAY_IN_SECS = 0.06
TWEET_SCROLL_DELAY_IN_SECS = 0.02
FONT = font5x7

# make FIFO queue
incoming_q = queue.Queue()

# init params
runtime = {"host": socket.gethostname().upper(), "is_first_run": 1}


def on_boot():
    """Display the hostname on the first run to identify the rpi"""
    ssid = check_output(['iwgetid']).split('ESSID:', 1)[1].strip()

    if runtime["is_first_run"] == 1:
        print("*** WEDPI ***")
        print(u"[INFO] We're online at {dt}".format(dt=time.strftime("%Y-%m-%d %H:%M")))
        print(u"[INFO] Hostname={host}".format(host=runtime["host"]))
        print(u"[INFO] Network={essid}".format(essid=ssid))
        print(u"[INFO] Waiting for tweets with {hashtag}...".format(hashtag=HASHTAG_TO_TRACK.upper()))
        print("*************")

        scrollphathd.clear()
        scrollphathd.show()

        length = scrollphathd.write_string(u'  ::: HOST >>> {host} :::  WIFI >>> {ssid} :::    '
                                           .format(host=runtime["host"], ssid=ssid), font=FONT, brightness=DISPLAY_BRIGHTNESS)
        length -= scrollphathd.width

        # Now for the scrolling loop...
        while length > 0:
            scrollphathd.scroll(1)  # Scroll the buffer one place to the left
            scrollphathd.show()  # Show the result
            length -= 1
            time.sleep(BOOT_SCROLL_DELAY_IN_SECS)  # Delay for each scrolling step

        runtime["is_first_run"] = 0
        time.sleep(5)


def reset():
    """Clear the display"""
    scrollphathd.clear()
    scrollphathd.show()


#
# MAIN
# define main loop to fetch formatted tweet from queue
#


def mainloop():
    scrollphathd.rotate(degrees=180)

    # On start-up display the hostname
    on_boot()
    reset()

    while True:
        # grab the tweet string from the queue
        try:
            scrollphathd.clear()
            status = incoming_q.get(False)
            scrollphathd.write_string(status, font=FONT, brightness=DISPLAY_BRIGHTNESS)
            status_length = scrollphathd.write_string(status, x=0, y=0, font=FONT, brightness=DISPLAY_BRIGHTNESS)
            time.sleep(0.25)

            while status_length > 0:
                scrollphathd.show()
                scrollphathd.scroll(1)
                status_length -= 1
                time.sleep(TWEET_SCROLL_DELAY_IN_SECS)

            reset()
            time.sleep(0.25)

            incoming_q.task_done()
            incoming_q.put(status)

            print("[DEBUG] Pending tweet queue size = " + str(incoming_q.qsize()))

        except queue.Empty:
            time.sleep(1)


class MyStreamListener(tweepy.StreamListener):
    def on_status(self, status):
        if not status.text.startswith('RT'):
            msg = status.text.upper().replace(HASHTAG_TO_TRACK.upper(), '')
            status = u'     >>>>>     @{name}: {text}     '.format(name=status.user.name.upper(), text=msg)

            try:
                status = unicodedata.normalize('NFKD', status).encode('ascii', 'ignore')
            except BaseException as e:
                print(e)

            # put tweet into the fifo queue
            incoming_q.put(status)

    def on_error(self, status_code):
        print("[ERROR] {}".format(status_code))
        if status_code == 420:
            return False


auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
auth.set_access_token(access_token, access_token_secret)
api = tweepy.API(auth)

myStreamListener = MyStreamListener()
myStream = tweepy.Stream(auth=api.auth, listener=myStreamListener)

myStream.filter(track=[HASHTAG_TO_TRACK], stall_warnings=True, async=True)

try:
    mainloop()

except KeyboardInterrupt:
    myStream.disconnect()
    del myStream
    del incoming_q
    print("Exiting!")
    exit()
