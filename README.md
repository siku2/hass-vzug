# V-ZUG Home Assistant Integration

[![GitHub Release](https://img.shields.io/github/release/siku2/hass-vzug.svg?style=for-the-badge)](https://github.com/siku2/hass-vzug/releases)
[![GitHub Activity](https://img.shields.io/github/commit-activity/y/siku2/hass-vzug.svg?style=for-the-badge)](https://github.com/siku2/hass-vzug/commits/main)
[![License](https://img.shields.io/github/license/siku2/hass-vzug.svg?style=for-the-badge)](LICENSE)

[![hacs](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://hacs.xyz/docs/faq/custom_repositories)

_Integration to integrate with [V-ZUG](https://www.vzug.com) devices._

**This integration will set up the following platforms.**

Platform | Description
-- | --
`sensor` | Eco management (water and energy usage) as well as the current program.
`update` | Allows you to update the firmware.

The following devices are fully supported:

- AdoraDish V6000
- AdoraWash V6000

## Installation

1. Add this repository as a custom repository to HACS: <https://hacs.xyz/docs/faq/custom_repositories>
2. Use HACS to install the integration.
3. Restart Home Assistant.
4. Set up the integration using the UI: [![Add Integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=vzug)

## Contributions are welcome!

If you want to contribute to this please read the [Contribution guidelines](CONTRIBUTING.md)
