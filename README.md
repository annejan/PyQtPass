# PyQtPass

PyQtPass is a graphical user interface built with PyQt5 for the `pass` password manager, leveraging the `passpy` library to provide a user-friendly way to interact with passwords stored securely on a Unix system.

## Features

- **Browse Passwords**: View your password entries in a tree structure that reflects the `pass` storage hierarchy.
- **Retrieve Passwords**: Double-click on an entry to view the corresponding password or secret.
- **Search and Filter**: Use the search box to filter out the entries you are looking for.
- **Cross-Platform**: Runs anywhere PyQt5 and `pass` can be installed.

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

## Contributing

Contributions to PyQtPass are welcome! Feel free to submit pull requests or open issues to suggest features or report bugs.

## License

### GNU GPL v3.0

[![GNU GPL v3.0](http://www.gnu.org/graphics/gplv3-127x51.png)](http://www.gnu.org/licenses/gpl.html)

[View official GNU site](http://www.gnu.org/licenses/gpl.html)

[<img src="https://opensource.org/wp-content/uploads/2022/10/osi-badge-dark.svg" alt="OSI-approved license" width="127">](https://opensource.org/licenses/GPL-3.0)

[View the Open Source Initiative site](https://opensource.org/licenses/GPL-3.0)

## Acknowledgments

- `pass`: The standard Unix password manager.
- `passpy`: A Python library for interacting with `pass`.

