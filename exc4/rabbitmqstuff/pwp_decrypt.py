import sys
from getpass import getpass
from Crypto.Cipher import AES

if __name__ == "__main__":
    try:
        fname = sys.argv[1]
    except IndexError:
        print("Specify file to decrypt as command line argument")
    else:
        with open(fname, "rb") as f:
            nonce = f.read(16)
            tag = f.read(16)
            ciphertext = f.read(-1)

        key = getpass("Input key:").encode("utf-8")
        cipher = AES.new(key, AES.MODE_EAX, nonce)
        print(cipher.decrypt_and_verify(ciphertext, tag).decode("utf-8"))


