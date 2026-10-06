===============================================================
  VIDEO ANALYZER
  Turn a YouTube link into screenshots with the time on each one
  Version 1.1
===============================================================

WHAT IT DOES
------------
You give it a YouTube link. It downloads the video and saves a
folder of screenshots taken at even spacing through it - roughly
30 of them - and every screenshot is named with the exact second
it came from. So "frame_0090.0s.jpg" really is the picture at
90 seconds.

It also writes a "manifest.json" listing every screenshot and its
timestamp, which is there for feeding to an AI along with a
transcript. If that means nothing to you, ignore it.


HOW TO USE IT
-------------
1. Double-click:   Video Analyzer.exe

2. Windows may show a blue box saying "Windows protected your PC".
   This is expected. It appears for any program that has not been
   through Microsoft's paid signing process - it is not a virus
   warning. Click "More info", then click "Run anyway".

3. Paste a YouTube link and press Add.

4. It shows you the video's title, length and how many screenshots
   it will make. Add more links if you want - they run one after
   another.

5. Press "Let's go".

6. When it finishes you get a grid of every screenshot. Click one
   to see it bigger. Press "Open folder" to find the files.

The app stays open. Press "Do another one" and go again.


TWO EXTRAS (new in version 1.1)
-------------------------------
JUST DOWNLOAD THE VIDEO
   At the top of the box where you paste the link there is a
   switch. Flip it to "Just download the video" and you get the
   video file only, no screenshots. In this mode it also accepts
   Instagram, Facebook and TikTok links, not only YouTube.

ALSO GET THE SCRIPT
   Tick "Also get the script" before pressing "Let's go" and it
   writes down everything that is said in the video, with the
   time next to each line. You get "transcript.txt" to read and
   "transcript.json" for feeding to an AI.

   Two things to expect:
   - The FIRST time you tick it, the app downloads its listening
     model - about 1.5 GB, once only. The bar will sit on
     "Warming up the transcriber" for a few minutes. It has not
     frozen. After that first time it starts straight away.
   - It does the listening on your computer's processor, so a
     long video takes a while - very roughly as long as the video
     itself on an ordinary laptop. Short clips take seconds.


WHERE DO THE PICTURES GO?
-------------------------
Into a "frames" folder right next to Video Analyzer.exe.

Each video gets its own folder, numbered in the order you did
them, like:

   frames\1 - Some Video Title - 25-8-2026\

So keep this whole folder somewhere sensible - your Desktop or
Documents is fine. Don't run it from inside the zip file.


DO I NEED TO INSTALL ANYTHING?
------------------------------
No. Everything it needs is inside this folder. (The one thing
it fetches by itself is the listening model for scripts - see
above - and only if you tick that box.)

The one exception, and it is rare: if you are on an older Windows
10 machine you may see a message asking for the "Microsoft Edge
WebView2 runtime". That is a free Microsoft download and the
message gives you the link. Windows 11 already has it.


IF SOMETHING GOES WRONG
-----------------------
The app tells you what happened in plain English - private video,
deleted video, no internet, and so on.

If the window will not open at all, there is a file called
"debug.log" in this folder. Send it over and it will usually say
exactly what stopped it.


A FEW THINGS WORTH KNOWING
--------------------------
- It downloads at 720p. Higher would be a waste for this purpose.
- The video file itself is kept next to the screenshots. If you
  don't want that, untick "Keep the video file" on the left.
- Long videos make more screenshots. A one-hour video makes about
  60. Anything up to half an hour makes 30 or fewer.
- Nothing is sent anywhere. It all happens on your computer.
