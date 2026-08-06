import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer
from desktop_pet import DesktopPet

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

pet = DesktopPet()

def save_screenshot():
    pet.grab().save("test_pet_typing.png")
    print("saved test_pet_typing.png")
    app.quit()

QTimer.singleShot(500, save_screenshot)
sys.exit(app.exec_())
