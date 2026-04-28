"""Mock local de la Shipping Status API para probar el camino feliz end-to-end.

No forma parte del producto. Util solo para validar la integracion sin
depender del backend real durante la demo. Levanta un servidor en localhost,
genera respuestas deterministas a partir del order_id y se apaga al matar el
proceso (Ctrl+C). El control_tower.py apunta aqui sobreescribiendo
SHIPPING_API_BASE via la variable de entorno SCF_SHIPPING_API_BASE.

Uso:
    python _mock_shipping_api.py 8000
    set SCF_SHIPPING_API_BASE=http://127.0.0.1:8000/api/shipping-status
    python control_tower.py --candidate-id SCF-2026-TEST ...
"""

from __future__ import annotations

import hashlib
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATUSES = [
    "label_created",
    "picked_up",
    "in_transit",
    "at_sorting_center",
    "out_for_delivery",
    "delivered",
    "delayed",
    "exception",
    "lost",
    "returned_to_sender",
]
REASONS = [
    "high_volume",
    "carrier_capacity_issue",
    "address_validation_error",
    "weather_disruption",
    "warehouse_delay",
    "customs_hold",
    "unknown",
]


def deterministic_payload(order_id: str) -> dict:
    h = hashlib.sha1(order_id.encode("utf-8")).digest()
    status = STATUSES[h[0] % len(STATUSES)]
    reason = REASONS[h[1] % len(REASONS)] if status in {"delayed", "exception"} else "unknown"
    risk = round((h[2] % 100) / 100.0, 2)
    manual = bool(h[3] % 4 == 0)
    eta = f"2026-04-{29 + (h[4] % 5):02d}"
    return {
        "order_id": order_id,
        "shipping_status": status,
        "delay_risk": risk,
        "delay_reason": reason,
        "estimated_delivery_date": eta,
        "requires_manual_review": manual,
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if not self.headers.get("X-Candidate-Id"):
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"error": "missing candidate id"}')
            return
        prefix = "/api/shipping-status/"
        if not self.path.startswith(prefix):
            self.send_response(404)
            self.end_headers()
            return
        order_id = self.path[len(prefix):].split("?")[0]
        payload = deterministic_payload(order_id)
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # silencio
        pass


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    with ThreadingHTTPServer(("127.0.0.1", port), Handler) as server:
        print(f"Mock shipping API listening on http://127.0.0.1:{port}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
