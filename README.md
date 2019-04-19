pyadb
=====

> A fork of [vmalyi/adb_android](https://github.com/vmalyi/adb_android)

Enables android adb in your python script.

### Purpose

This python package is a wrapper for standard android adb implementation. It allows you to execute android adb commands in your python script.

### What's supported?

Currently following adb commands are **supported**:
* adb -s
* adb push
* adb pull
* adb shell
* adb exec-out
* adb devices
* adb install
* adb uninstall
* adb get-serialno
* adb start-server
* adb kill-server
* adb get-state
* adb sync
* adb version
* adb bugreport
* adb wait-for-device

### What's not supported?

Currently following adb commands are **not supported**:

* adb forward
* adb logcat
* adb jdwp
* adb help
* adb -d
* adb -e

### What's TODO?

* Add background support for unterminated command
* Add adapters to provide more easy-to-use functions, e.g.
    * getprop (e.g., sdk version)
    * getevent
    * sendevent
    * input
    * ...

### How to install?

Download with help of git:

```
$ git clone https://github.com/Leetsong/pyadb.git
```

### How to use?

Put dir pyadb to your own project, a demo example (using [uiautomator](https://github.com/xiaocong/uiautomator)) shows here.

``` python
import uuid
from time import sleep
from datetime import datetime

from pyadb import Adb
from uiautomator import Device


def start_app(adb, emulator, app, main_component):
    adb.s(emulator).shell('am start-activity -n %s/%s' % (app, main_component))
    sleep(3)  # sleep, because all adb commands are nonblock


def dump_heap_and_pull(adb, emulator, pn, fn, gc: bool=False):
    tmp = "/data/local/tmp/" + str(uuid.uuid4())  # dump to a temp file
    adb.s(emulator).shell('am dumpheap %s %s %s' % ('-g' if gc else '', pn, tmp))
    sleep(3)  # sleep, because all adb commands are nonblock
    adb.s(emulator).pull(tmp, fn)  # pull to local
    adb.s(emulator).shell('rm %s' % tmp)  # remove the tmp file for release of space


if __name__ == '__main__':
    app = 'com.example'
    main_page = 'com.example.SplashActivity'
    emulator = 'emulator-5554'
    adb = Adb(enabled=True)
    d = Device(serial=emulator)

    # start the app
    start_app(adb, emulator, app, main_page)

    # run and dump heap
    counter = 0
    while True:
        while not d(text='Button 1').exists:
            pass
        print('[%d]: click button("Button 1")' % counter)
        d(text='Button 1?').click()

        while not d(textContains='Example Page').exists:
            pass
        print('[%d]: click button("<-")' % counter)
        d.press.back()

        if counter % 100 == 0:
            fn = 'heap-%s' % str(datetime.now())\
                .replace(' ', '-')\
                .replace(':', '-')\
                .replace('.', '-')
            print('[%d]: dump heap to %s' % (counter, fn))
            dump_heap_and_pull(adb, emulator, app, fn)

        counter = counter + 1

```

### How to contribute?

* Implement adb commands which are currently not supported by the module (see above)
* Bring your own ideas!
