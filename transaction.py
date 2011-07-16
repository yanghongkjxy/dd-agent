
import sys
import time
from datetime import datetime, timedelta
import logging
from operator import attrgetter

import tornado.ioloop

def plural(count):
    if count > 1:
        return "s"
    return ""

class Transaction(object):

    def __init__(self):

        self._id = None
        self._error_count = 0
        self._next_flush = datetime.now()        
        self._size = None

    def get_id(self):
        return self._id

    def set_id(self, new_id):
        assert self._id is None
        self._id = new_id

    def inc_error_count(self):
        self._error_count = self._error_count + 1

    def get_error_count(self):
        return self._error_count 

    def get_size(self):
        if self._size is None:
            self._size = sys.getsizeof(self)

        return self._size

    def get_next_flush(self):
        return self._next_flush

    def compute_next_flush(self,max_delay):
        # Transactions are replayed, try to send them faster for newer transactions
        # Send them every MAX_WAIT_FOR_REPLAY at most
        td = timedelta(seconds=self._error_count * 20)
        if td > max_delay:
            td = max_delay

        newdate = datetime.now() + td
        self._next_flush = newdate.replace(microsecond=0)

    def time_to_flush(self,now = datetime.now()):
        return self._next_flush < now

    def flush(self):
        raise ImplementationError("To be implemented in a subclass")

class TransactionManager(object):
    """Holds any transaction derived object list and make sure they
       are all commited, without exceeding parameters (throttling, memory consumption) """

    def __init__(self, max_wait_for_replay, max_queue_size, throttling_delay):

        self._MAX_WAIT_FOR_REPLAY = max_wait_for_replay
        self._MAX_QUEUE_SIZE = max_queue_size
        self._THROTTLING_DELAY = throttling_delay

        self._transactions = [] #List of all non commited transactions
    
        # Global counter to assign a number to each transaction: we may have an issue
        #  if this overlaps
        self._counter = 0

        self._trs_to_flush = None # Current transactions being flushed
        self._last_flush = datetime.now() # Last flush (for throttling)

    def get_tr_id(self):
        self._counter =  self._counter + 1
        return self._counter

    def append(self,tr):

        # Give the transaction an id
        tr.set_id(self.get_tr_id())

        # Check the size
        total_size = tr.get_size()
        if self._transactions is not None:
            for tr2 in self._transactions:
                total_size = total_size + tr2.get_size()

        logging.info("Adding transaction, total size of queue is: %s KB" % (total_size/1024))

        if total_size > self._MAX_QUEUE_SIZE:
            logging.warn("Queue is too big, removing old messages...")
            new_trs = sorted(self._transactions,key=attrgetter('_next_flush'), reverse = True)
            for tr2 in new_trs:
                if total_size > self._MAX_QUEUE_SIZE:
                    logging.warn("Removing transaction %s from queue" % tr2.get_id())
                    self._transactions.remove(tr2)
                    total_size = total_size - tr2.get_size()

        # Done
        self._transactions.append(tr)

    def flush(self):

        if self._trs_to_flush is not None:
            logging.info("A flush is already in progress, not doing anything")
            return

        to_flush = []
        # Do we have something to do ?
        now = datetime.now()
        for tr in self._transactions:
            if tr.time_to_flush(now):
                to_flush.append(tr)

        count = len(to_flush)
        if count > 0:
            logging.info("Flushing %s transaction%s" % (count,plural(count)))
            self._trs_to_flush = to_flush
            self.flush_next()

    def flush_next(self):

        if len(self._trs_to_flush) > 0:

            td = self._last_flush + self._THROTTLING_DELAY - datetime.now()
            # Python 2.7 has this built in, python < 2.7 don't...
            delay = (td.microseconds + (td.seconds + td.days * 24 * 3600) * 10**6) / 10.0**6
            if delay <= 0:
                tr = self._trs_to_flush.pop()
                self._last_flush = datetime.now()
                logging.debug("Flushing transaction %d" % tr.get_id())
                tr.flush()
            else:
                # Wait a little bit more
                tornado.ioloop.IOLoop.instance().add_timeout(time.time() + delay,
                    lambda: self.flush_next())
        else:
            self._trs_to_flush = None

    def tr_error(self,tr):
        tr.inc_error_count()
        tr.compute_next_flush(self._MAX_WAIT_FOR_REPLAY)
        logging.info("Transaction %d in error (%s error%s), it will be replayed after %s" %
          (tr.get_id(), tr.get_error_count(), plural(tr.get_error_count()), 
           tr.get_next_flush()))

    def tr_success(self,tr):
        logging.info("Transaction %d completed" % tr.get_id())
        self._transactions.remove(tr)


