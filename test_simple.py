import socket

# Check if port 8000 is open
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
result = sock.connect_ex(('localhost', 8000))

if result == 0:
    print(" Port 8000 is open - Server is running!")
else:
    print(" Port 8000 is closed - Server is NOT running")
    print("Run: python simple_honeypot.py")