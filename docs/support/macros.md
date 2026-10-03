# Support Macros

Copy, fill the `<...>` fields, and send. Keep the tone plain and friendly. Commands come from the
root [README](../../README.md); verify they still match before pasting.

## M1 - Need more info
> Thanks for reporting this. To dig in, could you send: your OS and version, how you installed
> (Windows Setup wizard or `python -m skeleton app install`), the exact command you ran, and the
> full error text? The output of `python -m skeleton app status` helps a lot too.

## M2 - Health check first
> Could you run these and paste the output?
> ```
> python -m skeleton app status --live
> python -m skeleton app check
> ```
> That tells us which part of the app isn't healthy.

## M3 - Services won't start (Docker)
> The app's services run in Docker, so Docker Desktop with the Compose plugin has to be installed
> and running, even with the Windows installer. Please start Docker Desktop, then run
> `python -m skeleton app up` again. If it still fails, send the output and we'll take it from there.

## M4 - Windows install problems
> Sorry the installer gave you trouble. Please try the repair option from the Start Menu
> shortcuts the installer created. If that doesn't help, uninstall, then run the latest
> `Skeleton-Setup-<version>-windows-x64.exe` again and tell us the version number you used.

## M5 - Known issue, tracked
> Thanks, this is a known issue we're tracking in <issue link>. <Workaround if any.> We'll update
> that issue when a fix ships.

## M6 - Logged as a bug
> Thanks, we could reproduce this and have logged it as <issue link>. We'll let you know when
> it's fixed.

## M7 - Incident in progress
> We're aware of a problem affecting <impact> and the team is on it. Latest status: <link>.
> No need to do anything else right now; we'll post when it's resolved.

## M8 - Resolved, please confirm
> A fix for this is out. Could you update and try again, and let us know if it's working for you?

## M9 - Feature request
> Thanks for the idea. I've passed it to the team as <issue link>. I can't promise a date, but
> requests like this do shape what gets built.
