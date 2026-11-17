# Original model visual laboratory

The authenticated optional full-model inspector now supports manual clip seeking at 0.1% normalized time increments, pause by explicit pose selection, restart of manual playback (unless reduced motion), and current-pose PNG export from the actual verified WebGL canvas. The PNG stays local; its temporary object URL is revoked on replacement, close, live return or unmount. The model and camera are unchanged by capture. Capture is not a simulation result or an external crawler event.

Measured browser render-interval and CPU render-submission times use a bounded rolling window (240 intervals); background gaps and paused states reset the window. These are not physical GPU timing or presentation FPS. No capture is automatically performed and no inspection writes crawl data. Original model still required. Actual rendering quality and timing need independent device qualification.
