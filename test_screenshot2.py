import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer
from desktop_pet import DesktopPet

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

pet = DesktopPet()
print("image_mode:", pet._image_mode)
print("pixmap is None:", pet._pixmap is None)
if pet._pixmap:
    print("pixmap size:", pet._pixmap.width(), "x", pet._pixmap.height())

def save_screenshot():
    pet.grab().save("test_pet_image_mode.png")
    print("saved test_pet_image_mode.png")
    app.quit()

QTimer.singleShot(500, save_screenshot)
sys.exit(app.exec_())
