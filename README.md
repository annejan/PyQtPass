# PyQtPass: Python Port of QtPass

## Introduction

<img align="right" src="artwork/icon.png" width="30%" />

Welcome to PyQtPass, an experimental and early-stage Python port of the renowned QtPass, originally developed in C++.
This initiative aims to leverage the versatility and simplicity of Python to enhance maintainability and extend the functionality of QtPass, a user-friendly GUI for `pass`, the standard Unix password manager.

QtPass has been a staple for users who prefer a graphical interface to manage their passwords securely and conveniently.
Recognizing the growing Python ecosystem and its powerful libraries, PyQtPass is an endeavor to transition the application from C++ to Python.
This move not only aligns with modern development practices but also opens up new avenues for features and improvements.

## Project Status: Experimental

Please note that PyQtPass is currently in an **early experimental phase**.
This means that while it encompasses the core functionalities of the original QtPass, it might not yet offer the full range of features, and you might encounter bugs or limitations that are typical in early-stage software.

We are actively developing PyQtPass and working towards a more stable and feature-rich version.
Your feedback and contributions during this phase are invaluable and will help shape the future of this project.

## Features

As of now, PyQtPass provides the following features:

- Graphical interface to interact with the `pass` password store.
- Tree view for password navigation.
- Password retrieval and display with a simple double-click action.
- Basic filtering capabilities to easily find specific passwords.
- Cross-platform compatibility, thanks to the Python and PyQt5 combination.

## Installation

Before running PyQtPass, ensure you have `pass` and `gpg` properly set up on your system. Then, follow these steps to get PyQtPass up and running:

1. Install the required Python packages:

   ```sh
   pip install PyQt5 passpy
   ```

2. Clone this repository:

   ```sh
   git clone https://github.com/annejan/PyQtPass.git
   ```

3. Navigate to the cloned directory and run the application:

   ```sh
   cd PyQtPass
   python main.py
   ```

## Usage

Upon launching PyQtPass, you will see a split interface.
On the left side is the tree view of your passwords, and on the right is the text area where the content of the selected password entry is displayed.
You can filter the entries using the search box above the tree view.

## Contributions and Feedback

We warmly welcome contributions, be it in the form of code, bug reports, suggestions, or documentation.

Since PyQtPass is in its experimental stage, your input is crucial for its refinement and progression.

Should you encounter any issues or have feature suggestions, please feel free to open an issue on our [GitHub issues page](https://github.com/annejan/PyQtPass/issues).

## License

### GNU GPL v3.0

[![GNU GPL v3.0](http://www.gnu.org/graphics/gplv3-127x51.png)](http://www.gnu.org/licenses/gpl.html)

[View official GNU site](http://www.gnu.org/licenses/gpl.html)

[<img src="https://opensource.org/wp-content/uploads/2022/10/osi-badge-dark.svg" alt="OSI-approved license" width="127">](https://opensource.org/licenses/GPL-3.0)

[View the Open Source Initiative site](https://opensource.org/licenses/GPL-3.0)

## Acknowledgments

- `pass`: The standard Unix password manager. For more information, visit [passwordstore.org](https://www.passwordstore.org/).
- `Qt Framework`: PyQtPass utilizes the Qt Framework, specifically Qt 5, a comprehensive set of C++ libraries and development tools that enable the creation of cross-platform applications.
  Discover more about the Qt Framework at [qt.io](https://www.qt.io/).
- `QtPass`: Qt GUI for Pass, written in C++, can be found at [qtpass.org](https://qtpass.org/).
- Co-Authorship: This project includes code and documentation co-written with the assistance of ChatGPT from OpenAI.
