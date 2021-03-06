#!/usr/bin/env python

import sys
import time

from oslo_config import cfg

from neutron.cmd.netns_cleanup import main

if __name__ == "__main__":
    while True:
        try:
            main()
            # Sleep for 12 hours
            time.sleep(43200)
        except Exception as ex:
            sys.stderr.write(
                "Cleaning network namespaces caught an exception %s"
                % str(ex))
            time.sleep(30)
        except:
            sys.stderr.write(
                "Cleaning network namespaces caught an exception")
            time.sleep(30)
        finally:
            cfg.CONF.clear()
