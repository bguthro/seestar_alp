# Seestar_Alp

Seestar ALP is a standalone controller, for command, control, and scheduling of SeeStar telescopes.

It uses a webpage based interface running on your computer, to interact with a backend server that controls the telescope.


### Where do I start?

That depends on your goals. (of course)

If you want to get in and learn the code and see how it all works then you can clone this git repository or download the code from the release, or from the main branch.  You will be interested in the ./device and ./front directories at first.

If you just want to use the GUI and commnicate with your Seestar then the standalone install may be right for you. The standalone install is described below.

## Installation

### Standalone package
For details on running pre-built standalone packages, please see the following wiki pages for the most up-to-date details:
- [Windows](https://github.com/smart-underworld/seestar_alp/wiki/Running-standalone:-Windows)
- [MacOS](https://github.com/smart-underworld/seestar_alp/wiki/Running-standalone:-Mac)
- [Linux](https://github.com/smart-underworld/seestar_alp/wiki/Running-Standalone:-Linux)

### Source code
For details on running from source, please see the following wiki pages for the most up-to-date details:
- [Raspberry Pi](https://github.com/smart-underworld/seestar_alp/wiki/Running-from-source:-Raspberry-Pi)
- [Mac](https://github.com/smart-underworld/seestar_alp/wiki/Running-from-source:-Mac)
- [Windows](https://github.com/smart-underworld/seestar_alp/wiki/Running-from-source:-Windows)


## How to get Support

I will set priority on responding from my Github and my Discord Channel:

Public Discord Channel for up to date info
<https://discord.gg/B3zDCAMP4V>

Github wiki pages
<https://github.com/smart-underworld/seestar_alp/wiki>

Facebook Group: Smart Telescope Underworld
<https://www.facebook.com/groups/373417055173095/>

YouTube Channel
<https://www.youtube.com/channel/UCASdbiZUKFGf6VR4H_mijxA>

Github source
<https://github.com/smart-underworld>

## Releases

Releases, and notes can be found on github at:
<https://github.com/smart-underworld/seestar_alp/releases>

## Optional scopinator integration

Seestar ALP can optionally delegate certain telescope commands to the
[scopinator](https://github.com/astrophotograph/pyscopinator) project when that
library is installed in the Python environment.  This can help reuse existing
client implementations or serve as a fallback transport when the native socket
connection is unreliable.

To enable the integration update `device/config.toml`:

```toml
[device]
use_scopinator = true          # enable the dynamic integration
scopinator_prefer = false      # leave false to prefer the built-in socket transport
scopinator_timeout = 15        # timeout (seconds) for synchronous scopinator calls
```

The same keys can be added to individual `[[seestars]]` entries to override the
defaults on a per-device basis.  When the module cannot be imported the driver
falls back to the existing socket implementation and logs an informational
message at startup.

