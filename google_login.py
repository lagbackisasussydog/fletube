import sys
import os

from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QLabel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl

COOKIES_OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "youtube_cookies.txt")

class LoginWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Log in to YouTube")
        self.resize(500, 750)

        self.collected_cookies = []

        central = QWidget()
        layout = QVBoxLayout(central)

        self.status_label = QLabel("Log in below, then click \"I'm done\" once you're on YouTube's homepage.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.web_view = QWebEngineView()
        layout.addWidget(self.web_view, stretch=1)

        self.done_button = QPushButton("I'm done — save session")
        self.done_button.clicked.connect(self.export_cookies)
        layout.addWidget(self.done_button)

        self.setCentralWidget(central)

        profile = self.web_view.page().profile()
        cookie_store = profile.cookieStore()
        cookie_store.cookieAdded.connect(self.on_cookie_added)

        self.web_view.load(QUrl(
            "https://accounts.google.com/ServiceLogin?service=youtube&continue=https://www.youtube.com/"
        ))

    def on_cookie_added(self, cookie):
        self.collected_cookies.append(cookie)

    def export_cookies(self):
        write_netscape_cookies(self.collected_cookies, COOKIES_OUTPUT_PATH)
        self.status_label.setText(f"Saved! You can close this window.")
        self.done_button.setText("Saved ✓")
        self.done_button.setEnabled(False)


def write_netscape_cookies(cookies, output_path):
    lines = ["# Netscape HTTP Cookie File", ""]

    for cookie in cookies:
        domain = cookie.domain()
        if not domain:
            continue

        include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
        path = cookie.path() or "/"
        secure = "TRUE" if cookie.isSecure() else "FALSE"
        expiry = int(cookie.expirationDate().toSecsSinceEpoch()) if not cookie.isSessionCookie() else 0
        name = bytes(cookie.name()).decode("utf-8", errors="ignore")
        value = bytes(cookie.value()).decode("utf-8", errors="ignore")

        line = f"{domain}\t{include_subdomains}\t{path}\t{secure}\t{expiry}\t{name}\t{value}"
        lines.append(line)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def run_login_flow():
    app = QApplication(sys.argv)
    window = LoginWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    run_login_flow()