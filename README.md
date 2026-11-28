# V-ZUG Home Assistant Integration

[![GitHub Release](https://img.shields.io/github/release/siku2/hass-vzug.svg?style=for-the-badge)](https://github.com/siku2/hass-vzug/releases)
[![GitHub Activity](https://img.shields.io/github/commit-activity/y/siku2/hass-vzug.svg?style=for-the-badge)](https://github.com/siku2/hass-vzug/commits/main)
[![License](https://img.shields.io/github/license/siku2/hass-vzug.svg?style=for-the-badge)](LICENSE)

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://hacs.xyz/docs/faq/custom_repositories)

[![GitLocalize](https://gitlocalize.com/repo/8875/whole_project/badge.svg)](https://gitlocalize.com/repo/8875/whole_project?utm_source=badge)

_Integration to integrate with [V-ZUG](https://www.vzug.com) devices._

The following devices are known to be supported:

- AdoraDish V2000 / V4000 / V6000[^1]
- AdoraDry V2000 / V4000 / V6000
- AdoraWash V2000 / V4000 / V6000[^1]
- Combair V4000 / V6000
- CombairSteamer V6000[^1]
- CombiCooler V4000
- CombiSteam HSL / MSLQ / XSL
- CombiSteamer V6000
- CookTop V6000
- Cooler V2000
- WineCooler V4000

[Check out the discussions](https://github.com/siku2/hass-vzug/discussions) for more info.
Don't hesitate to open a new issue or a discussion if you have a V-ZUG device you would like to add.

[^1]: Owned and tested by me. These are pretty much guaranteed to work.

## Installation

1. Add this repository as a custom repository to HACS: [![Add Repository](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=siku2&repository=hass-vzug&category=integration)
2. Use HACS to install the integration.
3. Restart Home Assistant.
4. Set up the integration using the UI: [![Add Integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=vzug)

Appliances that are already on your network are found by discovery or DHCP, or added by IP address. They don't need Bluetooth.

Optionally, a new appliance that isn't on your Wi-Fi yet can be set up over Bluetooth: switch on V-ZUG-Home in its user settings and Home Assistant discovers it and asks for your Wi-Fi (2.4 GHz only). This needs Home Assistant's Bluetooth integration with an adapter on the Home Assistant machine; pairing through Bluetooth proxies may not work. Without Bluetooth, everything else works as usual.

## Features

For every appliance:

- Firmware updates and notifications.
- All user settings are exposed as entities so you can modify the device settings on the fly.
- Program, program state and program end sensors.
- Errors shown on the appliance's display, its V-ZUG-Home mode and its cloud connection.
- Eco status (water and energy, including last month and last year).

By appliance type:

- **Dishwashers:** program selection with options and a delayed start, the options of the selected program, Stop.
- **Ovens, steamers and microwaves**[^2]: oven and food probe temperatures, preheating, door, probe inserted, oven light, kitchen timer, warming drawer, and program selection with temperature and duration.
- **Hobs**[^2]: power level and pan detection for each cooking zone. Read only, like in the V-ZUG app.
- **Refrigerators and wine cabinets:** zone temperatures, SuperCool / SuperFreeze / PartyCooling, holiday mode, Silent+, mono fridge, °C/°F, the wine cabinet's interior light and door openings.
- **Washing machines**[^2]: OptiDos detergent and dosage for both trays, tray levels, and whether laundry can still be added.
- **Washing machines and dryers:** program and status.

Like in the V-ZUG app, a selected program is only sent to the appliance; you start it there (close the dishwasher door, press start on the oven).

"Start program (experimental)" is disabled by default. It asks the appliance to start the selected program remotely, which the V-ZUG app never does, and the appliance may refuse. Only enable it if you accept an appliance starting with nobody there. Hobs never get it.

Some entities are disabled by default. Enable them under **Settings > Devices & services > V-ZUG > Entities**: the raw program end, the cloud connection, and the 7- and 30-day door opening averages.

[^2]: New and not yet confirmed on real appliances. Please report how it works with yours in an issue or a discussion.

## How the data is updated

The integration polls the appliance's local HTTP API. Nothing goes through the V-ZUG cloud.

- **State** (program, status, end, notifications): every 30 seconds while a program runs. Asking for the state wakes the appliance, so in standby only the notifications are read every minute. The full state is read every 5 minutes and when a new notification arrives.
- **Settings**: every hour, when a program starts or ends, and after every change from Home Assistant.
- **Programs**: every 5 minutes, and after every change from Home Assistant.
- **Zones** (refrigerators, ovens, hobs): every 30 seconds.
- **Firmware**: every 6 hours, and every 5 seconds during an update.

**Refresh now** reads everything at once and wakes the appliance. Use it after you change something on the appliance's panel.

An appliance that doesn't answer becomes unavailable until it answers again.

## Automation example

Notify when the dishwasher is done:

```yaml
automation:
  - alias: "Dishwasher done"
    triggers:
      - trigger: state
        entity_id: sensor.dishwasher_program
        not_from: ["standby", "active", "unavailable", "unknown"]
        to: ["standby", "active"]
    actions:
      - action: notify.mobile_app_phone
        data:
          message: "The dishwasher is done"
```

The entity IDs depend on the name of your appliance.

## Known limitations

- The appliance only accepts changes while V-ZUG-Home is set to "operate and display" in its user settings. Home Assistant shows a repair issue when it isn't.
- In standby the program, status and settings can be up to 5 minutes old.
- The names of the settings come from the appliance, in its language.
- Refrigerators report the set temperature only, not the measured one.
- Firmware updates only tell that a newer version exists, not which one.

## Troubleshooting

- **The appliance isn't found:** discovery only reaches appliances in the same network as Home Assistant. Add it by its IP address, and check that V-ZUG-Home is on in its user settings.
- **The entities are unavailable:** open `http://<ip address>/ai?command=getDeviceStatus` in a browser. If that doesn't answer either, the appliance is off the network. Some appliances switch off completely after a program. If the address changed, update it with **Reconfigure** in the menu (⋮) of the appliance.
- **Anything else:** enable debug logging on the integration's page, reproduce the problem, and open an [issue](https://github.com/siku2/hass-vzug/issues) with the log and the diagnostics. The diagnostics contain no passwords, serial numbers or addresses.

## Removal

1. Go to **Settings > Devices & services** and select **V-ZUG**.
2. Open the menu (⋮) of the appliance and select **Delete**. Repeat this for every appliance.
3. To remove the integration itself, open HACS, select **V-ZUG**, choose **Remove**, and restart Home Assistant.

Removing the integration doesn't change the appliance. An appliance you set up over Bluetooth stays on your Wi-Fi. To take it off the network, switch off V-ZUG-Home in its user settings.

## Contributions are welcome

If you want to contribute to this please read the [Contribution guidelines](CONTRIBUTING.md)

### Providing translations for other languages

If you would like to use the integration in another language, you can help out by providing the necessary translations.

[Head over to **GitLocalize** to start translating.](https://gitlocalize.com/repo/8875)

If your desired language isn't available there, just open an issue to request it.

You can also just do the translations manually in [custom_components/vzug/translations/](./custom_components/vzug/translations/) and open a pull request with the changes.
