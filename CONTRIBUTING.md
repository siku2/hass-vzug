# Contribution guidelines

Contributing to this project should be as easy and transparent as possible, whether it's:

- Reporting a bug
- Discussing the current state of the code
- Submitting a fix
- Proposing new features

## Github is used for everything

Github is used to host code, to track issues and feature requests, as well as accept pull requests.

Pull requests are the best way to propose changes to the codebase.

1. Fork the repo and create your branch from `main`.
2. If you've changed something, update the documentation.
3. Make sure your code lints (using `lint.sh`).
4. Test you contribution.
5. Issue that pull request!

## Any contributions you make will be under the MIT Software License

In short, when you submit code changes, your submissions are understood to be under the same [MIT License](http://choosealicense.com/licenses/mit/) that covers the project. Feel free to contact the maintainers if that's a concern.

## Report bugs using Github's [issues](../../issues)

GitHub issues are used to track public bugs.
Report a bug by [opening a new issue](../../issues/new/choose); it's that easy!

## Write bug reports with detail, background, and sample code

**Great Bug Reports** tend to have:

- A quick summary and/or background
- Steps to reproduce
  - Be specific!
  - Give sample code if you can.
- What you expected would happen
- What actually happens
- Notes (possibly including why you think this might be happening, or stuff you tried that didn't work)

People *love* thorough bug reports. I'm not even kidding.

## Debugging using VSCode

- After cloning the repo, VScode will detect the devcontainer setup and start to build one with docker desktop. Wait for completion. It may take a few minutes.
- The devcontainer is setup like this
  - A python base image
  - HomeAssistant is installed as a pip package
  - All the python dependencies are automatically installed using pip and requirements.txt
  - `PYTHONPATH` is set to prevent 'module not found on imports
  - `PROJECT_ROOT` is set to allow script and code execution independent of the working directory
  - File and remote debugging possibility are configured in launch.json
  
- The project comes with a device profiler and an emulator. To get an idea, run

    ```shell
    start_all_emulators.sh
    start_ha.sh
    ...
    stop_all_emulators.sh
    ```

  - Once HA is up and running, login and add V-Zug device on 127.0.0.1:5000 and 127.0.0.1:5001
  - In the terminal window you will see all the API calls done to the emulators
  
- To get API responses from a new device, simple run following command and follow the instructions

    ```shell
    collect_responses.sh
    ```
  
- Tests
  - The automated tests are automatically discovered by vscode. This is an ideal starting point for debugging
  
- Emulator
  - The emulator is currently read-only, i.e. only GET and no POST requests
  - The emulator is currently static, i.e. it does not support the pretty frequent 503 responses from the V-Zug appliances
  - The emulator can be accessed using Postman, and be debugged that way

## Use a Consistent Coding Style

Use [black](https://github.com/ambv/black) to make sure the code follows the style.
Sort your imports using [isort](https://pycqa.github.io/isort/).

## Test your code modification

For new devices, create profile, add a `expected.py`, and get the tests green

## License

This custom component is based on [integration_blueprint template](https://github.com/ludeeus/integration_blueprint).

By contributing, you agree that your contributions will be licensed under its MIT License.

## Pull updates from the template repository

```shell
# add the template repo as a remote
git remote add template https://github.com/siku2/hass-integration-template.git
git remote update
# merge changes
git merge --squash -e -Xtheirs --allow-unrelated-histories template/main
```shell
