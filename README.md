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

## Configuration

Setting up an appliance asks for:

| Parameter | When | Description |
| --- | --- | --- |
| Host | Manual setup | The IP address or host name of the appliance, ex. `192.168.1.42`. A full URL like `https://192.168.1.42` works too, without a scheme `http://` is used. Give the appliance a fixed address in your router; if it changes anyway, DHCP discovery usually picks up the new one. |
| Username, Password | Only if the appliance asks for them | The credentials of the appliance's web interface, if you protected it with a password. If they change later, Home Assistant asks for the new ones (re-authentication). |
| Wi-Fi name (SSID), Wi-Fi password | Bluetooth setup only | The 2.4 GHz network the appliance joins. They are sent to the appliance over Bluetooth and not stored in Home Assistant. |

Discovery (**Add integration → V-ZUG → Discovery**) broadcasts on every network adapter Home Assistant uses and offers each appliance that answers; appliances on another subnet or VLAN have to be added manually.

The integration has no options. Everything you can change on the appliance is an entity of its device.

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

Some entities are disabled by default, enable them under **Settings → Devices & services → V-ZUG → Entities** if you need them: the raw program end, the cloud connection, the 7- and 30-day door opening averages, the read-only values of the appliance settings (they mostly repeat the eco sensors as display text), and the actions in the appliance settings, ex. resetting the consumption statistics.

[^2]: New and not yet confirmed on real appliances. Please report how it works with yours in an issue or a discussion.

## How the data is updated

The appliances have a local HTTP API; the integration polls it, nothing goes through the V-ZUG cloud.

- **State** (program, status, end, notifications): every 30 seconds while the appliance is running. In standby only the notifications are read every minute, because asking for the state wakes the appliance up and it would never sleep; the full state is read every 5 minutes, and right away when a new notification arrives (a program started or finished).
- **Settings** (the category tree): every hour, when a program starts or ends, and after every change from Home Assistant. Settings that appear later, ex. after a firmware update, become entities on their own.
- **Programs** (selected program and its options): every 5 minutes, and after every change from Home Assistant.
- **Zones** (refrigerators, ovens, hobs): every 30 seconds.
- **Firmware**: every 6 hours, every 5 seconds during an update.

**Refresh now** reads everything at once and wakes the appliance up; use it after changing something on the appliance's panel, or in an automation that knows better (a smart plug, a door contact).

An appliance that doesn't answer at all becomes unavailable, and is back with the next answer. A single failed request doesn't: the appliances fail one now and then, the integration retries and keeps the last values for a few polls.

## Use cases

- Get a notification on your phone when the dishwasher or the washing machine is done, or when it needs rinse aid or salt (**Last notification**).
- Show when the program ends (**Program end**) on a dashboard or a smart display.
- Start the dishwasher at night, when electricity is cheap: select the program and a **Start delay**, then **Send to appliance**; it starts once the door is closed.
- Track water and energy per program with the eco sensors, ex. in the energy dashboard.
- Switch the refrigerator to holiday mode with your alarm system, or SuperCool before the groceries arrive.
- Get a warning when the fridge or freezer door stays open.

## Automation examples

Notify when a program ends:

```yaml
automation:
  - alias: "Dishwasher done"
    triggers:
      - trigger: state
        entity_id: sensor.dishwasher_program
        to: "standby"
        not_from: ["unavailable", "unknown"]
    actions:
      - action: notify.mobile_app_phone
        data:
          message: "{{ states('sensor.dishwasher_last_notification') }}"
```

Warn about an open freezer door:

```yaml
automation:
  - alias: "Freezer door open"
    triggers:
      - trigger: state
        entity_id: binary_sensor.fridge_freezer_door
        to: "on"
        for: "00:02:00"
    actions:
      - action: notify.mobile_app_phone
        data:
          message: "The freezer door has been open for 2 minutes"
```

Run the dishwasher with the Eco program, 3 hours from now:

```yaml
script:
  dishwasher_eco_later:
    sequence:
      - action: select.select_option
        target:
          entity_id: select.dishwasher_program_selection
        data:
          option: eco
      - action: number.set_value
        target:
          entity_id: number.dishwasher_start_delay
        data:
          value: 3
      - action: button.press
        target:
          entity_id: button.dishwasher_send_to_appliance
```

The entity IDs depend on the name of your appliance.

## Known limitations

- Programs can't be started remotely, like in the V-ZUG app: **Send to appliance** transfers the program, you start it at the appliance (close the dishwasher door, press start on the oven). The experimental **Start program** asks the appliance anyway, many refuse.
- The appliance only takes changes while V-ZUG-Home is set to "operate and display" in its user settings. Otherwise Home Assistant shows a repair issue, and changes fail.
- In standby the program, status and settings can be up to 5 minutes old, see [How the data is updated](#how-the-data-is-updated).
- The appliances handle one request at a time and fail one now and then, more so when they are busy. The integration retries; a slow network or a weak Wi-Fi makes this worse.
- The names of the settings come from the appliance, in the language it is set to.
- Refrigerators report the set temperature only, not the measured one.
- Firmware updates only tell that a newer version exists, not which one.
- Bluetooth setup needs an adapter on the Home Assistant machine, proxies may not be able to pair; the appliance only joins 2.4 GHz Wi-Fi.

## Troubleshooting

- **The appliance isn't found:** discovery only reaches appliances in the same network as Home Assistant. Add it by its IP address (see your router), and make sure V-ZUG-Home is switched on in its user settings.
- **"Failed to connect" / the entities are unavailable:** open `http://<ip address>/ai?command=getDeviceStatus` in a browser on the same network. If that doesn't answer either, the appliance is off the network: some switch off completely after a program, others lose Wi-Fi. If the address changed, update it under **⋮ → Reconfigure**.
- **Changes fail with "The appliance refused the request":** set V-ZUG-Home to "operate and display" on the appliance, a repair issue in Home Assistant tells you when it isn't.
- **"Authentication failed":** the appliance's web interface is protected; enter the user name and password set on the appliance. When they change, Home Assistant asks for the new ones.
- **Bluetooth setup fails:** stay close to the appliance, use an adapter on the Home Assistant machine, and check the Wi-Fi name and password (2.4 GHz only).
- **Anything else:** enable debug logging on the integration's page (**⋮ → Enable debug logging**), reproduce the problem, disable it again, and open an [issue](https://github.com/siku2/hass-vzug/issues) with the log and the diagnostics (**⋮ → Download diagnostics**); they contain no passwords, serial numbers or addresses.

## Removal

1. Go to **Settings → Devices & services** and select **V-ZUG**.
2. Open the menu (⋮) of the appliance and select **Delete**. Repeat this for every appliance.
3. To remove the integration itself, open HACS, select **V-ZUG**, choose **Remove**, and restart Home Assistant.

Removing the integration doesn't change anything on the appliance. If you set it up over Bluetooth, it stays on your Wi-Fi; switch V-ZUG-Home off in its user settings if you no longer want it on the network.

## Contributions are welcome

If you want to contribute to this please read the [Contribution guidelines](CONTRIBUTING.md)

### Providing translations for other languages

If you would like to use the integration in another language, you can help out by providing the necessary translations.

[Head over to **GitLocalize** to start translating.](https://gitlocalize.com/repo/8875)

If your desired language isn't available there, just open an issue to request it.

You can also just do the translations manually in [custom_components/vzug/translations/](./custom_components/vzug/translations/) and open a pull request with the changes.
