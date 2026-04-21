import sys
import time

try:
    import serial
    import serial.tools.list_ports
except ImportError as e:
    print("ERROR: pyserial no está instalado. Ejecuta:")
    print("  pip install pyserial")
    sys.exit(1)


def list_ports():
    print("=== Puertos serie disponibles ===")
    for p in serial.tools.list_ports.comports():
        print(f"  {p.device}: {p.description} ({p.manufacturer})")
    print("=================================")


def main():
    list_ports()

    if len(sys.argv) < 3:
        print("\nUso:")
        print("  python test_serial_debug.py COMx 921600")
        print("Ejemplo:")
        print("  python test_serial_debug.py COM6 921600")
        return

    port = sys.argv[1]
    try:
        baud = int(sys.argv[2])
    except ValueError:
        print("Baudios inválidos, usando 921600.")
        baud = 921600

    print(f"\nIntentando abrir {port} a {baud} baudios...")
    try:
        ser = serial.Serial(
            port=port,
            baudrate=baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.2,
            write_timeout=1.0,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )
    except Exception as e:
        print(f"ERROR al abrir el puerto: {e}")
        return

    print(f"Puerto abierto: {ser.portstr}")
    print(f"  baudrate  = {ser.baudrate}")
    print(f"  bytesize  = {ser.bytesize}")
    print(f"  parity    = {ser.parity}")
    print(f"  stopbits  = {ser.stopbits}")
    print(f"  xonxoff   = {ser.xonxoff}")
    print(f"  rtscts    = {ser.rtscts}")
    print(f"  dsrdtr    = {ser.dsrdtr}")

    # Limpiamos buffers antes de nada.
    try:
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        print("Buffers RX/TX limpiados.")
    except Exception as e:
        print(f"Advertencia: no se pudieron limpiar buffers: {e}")

    # Enviar 'A' como prueba, igual que haces en Tera Term.
    try:
        print("\nEnviando byte 'A' (0x41)...")
        n = ser.write(b"A")
        ser.flush()
        print(f"Bytes escritos: {n}")
    except Exception as e:
        print(f"ERROR al escribir en el puerto: {e}")
        ser.close()
        return

    print("\nLeyendo respuesta durante 3 segundos...")
    start = time.time()
    total = 0
    while time.time() - start < 3.0:
        try:
            waiting = ser.in_waiting
        except Exception as e:
            print(f"ERROR al consultar in_waiting: {e}")
            break

        if waiting:
            try:
                data = ser.read(waiting)
            except Exception as e:
                print(f"ERROR al leer datos: {e}")
                break
            total += len(data)
            print(f"RX ({len(data)} bytes): {data!r} | hex={data.hex()}")
        else:
            time.sleep(0.05)

    print(f"\nTotal de bytes recibidos en 3s: {total}")
    ser.close()
    print("Puerto cerrado.")


if __name__ == "__main__":
    main()

