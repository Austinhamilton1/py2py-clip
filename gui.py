import tkinter as tk
from tkinter import ttk
import threading
import asyncio

from server import server
from client import client


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("py2py-clip")

        self.loop = None
        self.thread = None

        # Mode selection
        self.mode = tk.StringVar(value="client")

        ttk.Label(root, text="Mode").grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(root, text="Client", variable=self.mode, value="client", command=self.update_ui).grid(row=0, column=1)
        ttk.Radiobutton(root, text="Server", variable=self.mode, value="server", command=self.update_ui).grid(row=0, column=2)
        ttk.Radiobutton(root, text="Both", variable=self.mode, value="both", command=self.update_ui).grid(row=0, column=3)

        # Client config
        ttk.Label(root, text="Remote IP").grid(row=1, column=0)
        self.ip_entry = ttk.Entry(root)
        self.ip_entry.insert(0, "127.0.0.1")
        self.ip_entry.grid(row=1, column=1, columnspan=2)

        ttk.Label(root, text="Remote Port").grid(row=2, column=0)
        self.remote_port_entry = ttk.Entry(root)
        self.remote_port_entry.insert(0, "5000")
        self.remote_port_entry.grid(row=2, column=1, columnspan=2)

        # Server config
        ttk.Label(root, text="Server Port").grid(row=3, column=0)
        self.server_port_entry = ttk.Entry(root)
        self.server_port_entry.insert(0, "5000")
        self.server_port_entry.grid(row=3, column=1, columnspan=2)

        # Buttons
        self.start_btn = ttk.Button(root, text="Start", command=self.start)
        self.start_btn.grid(row=4, column=1)

        self.stop_btn = ttk.Button(root, text="Stop", command=self.stop, state="disabled")
        self.stop_btn.grid(row=4, column=2)

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.update_ui()

    def start(self):
        mode = self.mode.get()
        ip = self.ip_entry.get()
        remote_port = int(self.remote_port_entry.get())
        server_port = int(self.server_port_entry.get())

        self.loop = asyncio.new_event_loop()

        def run_loop():
            asyncio.set_event_loop(self.loop)

            tasks = []

            if mode == "client":
                tasks.append(self.loop.create_task(client(ip, remote_port)))

            elif mode == "server":
                tasks.append(self.loop.create_task(server(server_port)))

            elif mode == "both":
                tasks.append(self.loop.create_task(server(server_port)))
                tasks.append(self.loop.create_task(client("127.0.0.1", server_port)))

            try:
                self.loop.run_until_complete(asyncio.gather(*tasks))
            except asyncio.CancelledError:
                pass

        self.thread = threading.Thread(target=run_loop, daemon=True)
        self.thread.start()

        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")

    def stop(self):
        if self.loop:
            for task in asyncio.all_tasks(loop=self.loop):
                task.cancel()

            self.loop.call_soon_threadsafe(self.loop.stop)

        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")

    def on_close(self):
        self.stop()
        self.root.destroy()

    def update_ui(self):
        mode = self.mode.get()

        if mode == "client":
            # Enable client fields
            self.ip_entry.config(state="normal")
            self.remote_port_entry.config(state="normal")

            # Disable server fields
            self.server_port_entry.config(state="disabled")

        elif mode == "server":
            # Disable client fields
            self.ip_entry.config(state="disabled")
            self.remote_port_entry.config(state="disabled")

            # Enable server fields
            self.server_port_entry.config(state="normal")

        elif mode == "both":
            # Server port is needed
            self.server_port_entry.config(state="normal")

            # Client connects locally → no need for manual input
            self.ip_entry.config(state="disabled")
            self.remote_port_entry.config(state="disabled")


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()