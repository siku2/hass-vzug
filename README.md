# V-ZUG Home Assistant Integration

[![GitHub Release](https://img.shields.io/github/release/siku2/hass-vzug.svg?style=for-the-badge)](https://github.com/siku2/hass-vzug/releases)
[![GitHub Activity](https://img.shields.io/github/commit-activity/y/siku2/hass-vzug.svg?style=for-the-badge)](https://github.com/siku2/hass-vzug/commits/main)
[![License](https://img.shields.io/github/license/siku2/hass-vzug.svg?style=for-the-badge)](LICENSE)

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://hacs.xyz/docs/faq/custom_repositories)

[![GitLocalize](https://gitlocalize.com/repo/8875/whole_project/badge.svg)](https://gitlocalize.com/repo/8875/whole_project?utm_source=badge)

_Integration to integrate with [V-ZUG](https://www.vzug.com) devices._

The following devices are known to be supported:

- AdoraDish V2000 / V4000 / V6000
- AdoraDry V2000
- AdoraWash V2000 / V4000 / V6000
- Combi-Steam HSL / MSLQ
- CombiCooler V4000

I would love to add more devices to this list. Don't hesitate to open a new issue or a discussion if you have a V-ZUG device you would like to add.

## Installation

1. Add this repository as a custom repository to HACS: [![Add Repository](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=siku2&repository=hass-vzug&category=integration)
2. Use HACS to install the integration.
3. Restart Home Assistant.
4. Set up the integration using the UI: [![Add Integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=vzug)

## Features

- Firmware updates and notifications.
- All user settings are exposed as entites so you can modify the device settings on the fly.
- Program and program end sensors.
- Eco status.

## Contributions are welcome

If you want to contribute to this please read the [Contribution guidelines](CONTRIBUTING.md)

### Providing translations for other languages

If you would like to use the integration in another language, you can help out by providing the necessary translations.

[Head over to **GitLocalize** to start translating.](https://gitlocalize.com/repo/8875)

If your desired language isn't available there, just open an issue to request it.

You can also just do the translations manually in [custom_components/vzug/translations/](./custom_components/vzug/translations/) and open a pull request with the changes.
