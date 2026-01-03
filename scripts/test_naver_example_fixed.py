import bcrypt
import base64

clientId = "aaaabbbbcccc"
clientSecret = "$2a$10$abcdefghijklmnopqrstuv"
timestamp = 1643961623299

password = clientId + "_" + str(timestamp)
hashed = bcrypt.hashpw(password.encode('utf-8'), clientSecret.encode('utf-8'))
sig = base64.b64encode(hashed).decode('utf-8')

print(f"Generated: {sig}")
print(f"Expected:  JDJhJDEwJGFiY2RlZmdoaWprbG1ub3BxcnN0dXVCVldZSk42T0VPdEx1OFY0cDQxa2IuTnpVaUEzbmsy")
