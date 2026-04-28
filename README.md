ECG KeyGen & Device Bridge — Python CoreProfessional Python-based application designed for real-time ECG signal acquisition and cryptographic key generation. This tool interfaces directly with ECG monitoring hardware to transform physiological data into secure, real-time keys.Core FunctionalitiesECG Data Acquisition: High-speed sampling via UART (Serial) and Bluetooth Low Energy (BLE).Real-Time Key Generation: Integrated logic to process ECG waveforms and generate cryptographic entropy or keys on-the-fly.Python-Native Architecture: Built for seamless integration with data science and ML pipelines (NumPy, SciPy, Scikit-learn).Cross-Platform: Optimized for high performance on both standard Desktop environments and Edge devices (Raspberry Pi/Nvidia Jetson).PrerequisitesPython 3.10+ (recommended).Linux/Raspbian Users: Ensure your user has permissions for serial and Bluetooth stacks (see Raspbian Configuration).InstallationBash# Clone the repository and enter the directory
cd ecg-device-bridge

# Create and activate a virtual environment
python3 -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install production dependencies
pip install -r requirements.txt
Running the ApplicationTo launch the graphical interface and data processing engine:Bashpython app.py
Operational ModesUART / Serial InterfaceNavigate to the "UART / Serial" tab.Refresh the port list and select the COM port corresponding to your ECG reader.Set the appropriate baud rate and click "Open".The real-time ECG stream will begin populating the log and the processing engine.Bluetooth (BLE) InterfaceNavigate to the "Bluetooth (BLE)" tab.Click "Scan" to discover nearby ECG devices.Connect to the target device and enable notifications for the specific Service/Characteristic UUIDs.Project Structureapp.py: Main application entry point and Tkinter-based GUI.serial_handler.py: High-performance serial communication via PySerial.ble_handler.py: Asynchronous BLE management using Bleak.key_generator.py: (Logic module) Processes ECG signals to generate cryptographic keys.requirements.txt: Project dependencies (PySerial, Bleak, NumPy, etc.).Deployment: Building Standalone ExecutablesYou can generate a standalone binary so that end-users do not need to install Python or manage dependencies.For Linux EnvironmentsSetup Build Environment:Bashpip install -r requirements-build.txt
Generate Binary:Bashchmod +x build_linux.sh
./build_linux.sh
Distribution: The executable is located in dist/DeviceBridge/. You can move this entire folder to any compatible Linux system.For Windows EnvironmentsSetup Build Environment:PowerShellpip install -r requirements-build.txt
Generate Binary:PowerShellpython -m PyInstaller --clean --noconfirm app.spec
Distribution: The standalone DeviceBridge.exe and its required DLLs will be generated in dist\DeviceBridge\.Raspbian ConfigurationTo ensure low-level hardware access on Raspberry Pi OS:Serial Access:Bashsudo usermod -a -G dialout $USER
(Logout and login for changes to take effect).Bluetooth Stack:Bashsudo apt install libbluetooth-dev
sudo setcap cap_net_raw+eip $(readlink -f $(which python3))
Technical SpecificationsFeatureSpecificationPrimary LanguagePython 3.10Serial ProtocolPySerial (Asynchronous polling)Bluetooth ProtocolBleak (Bluetooth Low Energy)GUI FrameworkTkinterSignal ProcessingReal-time stream processing for KeyGen
