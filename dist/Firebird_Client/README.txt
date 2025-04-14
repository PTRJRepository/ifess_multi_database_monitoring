# Firebird Client Application

## Overview
This is a standalone client application for connecting to Firebird databases and executing SQL queries.

## Features
- Connect to Firebird databases using localhost format
- Execute custom SQL queries
- View query results in a formatted display
- Save and load SQL queries
- Export query results to CSV files

## How to Use
1. Double-click on `Firebird_Client.exe` or `Run_Firebird_Client.bat` to start the application
2. In the application:
   - Enter the database path (default: C:\Gawean Rebinmas\Monitoring Database\Ifess Monitoring\PTRJ_P1A_08042025\PTRJ_P1A.FDB)
   - Enter the ISQL path (default: C:\Program Files (x86)\Firebird\Firebird_1_5\bin\isql.exe)
   - Enter the username (default: sysdba)
   - Enter the password (default: masterkey)
   - Click "Connect" to connect to the database
3. Once connected, you can:
   - Go to the "SQL Query Editor" tab to write and execute SQL queries
   - View query results in the results area
   - Save queries and export results using the buttons in the toolbar

## Default Connection Settings
- Database Path: C:\Gawean Rebinmas\Monitoring Database\Ifess Monitoring\PTRJ_P1A_08042025\PTRJ_P1A.FDB
- ISQL Path: C:\Program Files (x86)\Firebird\Firebird_1_5\bin\isql.exe
- Username: sysdba
- Password: masterkey
- Connection Format: localhost (recommended)

## Troubleshooting
If you encounter any issues:
1. Make sure the Firebird server is running
2. Check that the database path is correct
3. Verify that the ISQL path points to the correct isql.exe file
4. Ensure that the username and password are correct
5. Try using the localhost connection format (recommended)

## Notes
- This application is a standalone executable and does not require Python or any additional packages to be installed
- All necessary dependencies are included in the executable
