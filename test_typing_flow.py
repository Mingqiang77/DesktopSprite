import sys
import time
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer
from desktop_pet import DesktopPet
from pynput.keyboard import Controller

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

pet = DesktopPet()

kb = Controller()

def step1():
    print("state before keys:", pet.state)
    # simulate typing
    for i in range(8):
        kb.press('a')
        kb.release('a')
        time.sleep(0.05)
    print("sent keys")
    QTimer.singleShot(800, step2)

def step2():
    print("state after keys:", pet.state)
    pet.grab().save("test_typing_flow.png")
    print("saved test_typing_flow.png")
    app.quit()

QTimer.singleShot(500, step1)
sys.exit(app.exec_())
