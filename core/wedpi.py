#!/usr/bin/env python

import logging
import os
import socket
import time
import unicodedata

logging.basicConfig(filename='/tmp/wedpi-app.log', level=logging.DEBUG,
                    format='%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s', datefmt='%d-%b-%y %H:%M:%S')

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

HASHTAG_TO_TRACK = str(os.getenv('WEDPI_HASHTAG_TO_TRACK', '#tuffwed'))
USER_TO_TRACK = str(os.getenv('WEDPI_USER_TO_TRACK', '1132584694711762944'))
DISPLAY_BRIGHTNESS = float(os.getenv('WEDPI_DISPLAY_BRIGHTNESS', 0.2))
BOOT_SCROLL_DELAY_IN_SECS = float(os.getenv('WEDPI_BOOT_SCROLL_DELAY_IN_SECS', 0.06))
TWEET_SCROLL_DELAY_IN_SECS = float(os.getenv('WEDPI_TWEET_SCROLL_DELAY_IN_SECS', 0.02))
FONT = font5x7


class MutableQueue(queue.Queue):
    """Extend the Queue to introduce a clear() method"""

    def clear(self):
        """
        Clears all items from the queue.
        """

        with self.mutex:
            unfinished = self.unfinished_tasks - len(self.queue)
            if unfinished <= 0:
                if unfinished < 0:
                    raise ValueError('task_done() called too many times')
                self.all_tasks_done.notify_all()
            self.unfinished_tasks = unfinished
            self.queue.clear()
            self.not_full.notify_all()


# make FIFO queue
incoming_q = MutableQueue()


def prepare_msg(text):
    status = u'     {msg}     '.format(msg=text.upper())
    try:
        return unicodedata.normalize('NFKD', status).encode('ascii', 'ignore')
    except BaseException:
        logging.exception("Failed to encode message")


def init_queue():
    global incoming_q
    logging.debug("Reinitialising the queue...")
    incoming_q.clear()
    incoming_q.put(prepare_msg(u"Welcome to Chemayne & Lewis's wedding"))
    incoming_q.put(prepare_msg(u"Saturday 8th June 2019"))
    incoming_q.put(prepare_msg(u"Tweet us using hashtag #tuffwed"))


# initialise runtime params
runtime = {"host": socket.gethostname().upper(), "is_first_run": 1}


def on_boot():
    """Display the hostname on the first run to identify the rpi"""
    ssid = check_output(['iwgetid']).split('ESSID:', 1)[1].strip()

    if runtime["is_first_run"] == 1:
        logging.debug("*** WEDPI ***")
        logging.debug(u"We're online at {dt}".format(dt=time.strftime("%Y-%m-%d %H:%M")))
        logging.debug(u"Hostname={host}".format(host=runtime["host"]))
        logging.debug(u"Network={essid}".format(essid=ssid))
        logging.debug(u"Waiting for tweets with {hashtag}...".format(hashtag=HASHTAG_TO_TRACK.upper()))
        logging.debug("*************")

        scrollphathd.clear()
        scrollphathd.show()

        length = scrollphathd.write_string(u'  ::: HOST >>> {host} :::  WIFI >>> {ssid} :::    '
                                           .format(host=runtime["host"], ssid=ssid), font=FONT,
                                           brightness=DISPLAY_BRIGHTNESS)
        length -= scrollphathd.width

        scroll(length)

        runtime["is_first_run"] = 0
        time.sleep(5)


def reset():
    """Clear the display"""
    scrollphathd.clear()
    scrollphathd.show()


def scroll(length):
    while length > 0:
        scrollphathd.show()
        scrollphathd.scroll(1)
        length -= 1
        time.sleep(TWEET_SCROLL_DELAY_IN_SECS)


#
# MAIN
# define main loop to fetch formatted tweet from queue
#


def mainloop():
    scrollphathd.rotate(degrees=180)

    # On start-up display the hostname
    on_boot()
    init_queue()
    reset()

    while True:
        # grab the tweet string from the queue
        try:
            scrollphathd.clear()
            status = incoming_q.get(False)

            # if we receive a :CLEAR command reinitialise the queue
            if ':CLEAR' in status:
                init_queue()
                continue

            scrollphathd.write_string(status, font=FONT, brightness=DISPLAY_BRIGHTNESS)
            status_length = scrollphathd.write_string(status, x=0, y=0, font=FONT, brightness=DISPLAY_BRIGHTNESS)
            time.sleep(0.25)

            scroll(status_length)

            reset()
            time.sleep(0.25)

            incoming_q.task_done()
            incoming_q.put(status)

            logging.debug(u'Pending tweet queue size = {}'.format(str(incoming_q.qsize())))

        except queue.Empty:
            time.sleep(1)

        except Exception:
            logging.exception("Something went wrong in mainloop()")


class MyStreamListener(tweepy.StreamListener):
    def on_status(self, status):
        logging.debug(u'status = {0}>{1}'.format(status.user.name, status.text))

        if not status.text.startswith('RT'):
            msg = status.text.upper().replace(HASHTAG_TO_TRACK.upper(), '')
            status = u'     >>>>>     @{name}: {text}     '.format(name=status.user.name.upper(), text=msg)

            try:
                status = unicodedata.normalize('NFKD', status).encode('ascii', 'ignore')
            except BaseException as e:
                logging.exception(e)

            # put tweet into the fifo queue
            incoming_q.put(status)

    def on_error(self, status_code):
        logging.error("Error {}".format(status_code))
        if status_code == 420:
            return False


auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
auth.set_access_token(access_token, access_token_secret)
api = tweepy.API(auth)

myStreamListener = MyStreamListener()
myStream = tweepy.Stream(auth=api.auth, listener=myStreamListener)
myStream.filter(track=[HASHTAG_TO_TRACK], follow=[USER_TO_TRACK], stall_warnings=True, async=True)

try:
    mainloop()

except KeyboardInterrupt:
    logging.warn("Exiting!")

except Exception:
    logging.exception("Something went wrong")

finally:
    myStream.disconnect()
    del myStream
    del incoming_q
    exit()
