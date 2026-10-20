"""
Optional provisioning through the Zabbix JSON-RPC API.

The sender does NOT need this. It only creates the host group and one host
per INspektor, linked to the right template, so the customer does not have
to click through the web UI. Requires an API token with rights to create
hosts in the target group.

Authentication changed across versions, so we ask the server first:
    apiinfo.version   works without authentication on every version
    >= 6.4            token in 'Authorization: Bearer <token>' header
    5.4 to 6.2        token in the 'auth' field of the request body
    < 5.4             no API tokens at all, unsupported here
"""

import json
import urllib.request
import urllib.error


class ZabbixApiError(Exception):
    pass


def _ver_tuple(v: str):
    parts = []
    for p in v.split(".")[:3]:
        num = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(num) if num else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


class ZabbixApi:
    def __init__(self, url: str, token: str, timeout: float = 15.0):
        if not url.endswith("api_jsonrpc.php"):
            url = url.rstrip("/") + "/api_jsonrpc.php"
        self.url = url
        self.token = token
        self.timeout = timeout
        self._id = 0
        self.version = self._raw_call("apiinfo.version", {}, auth=False)
        self.vt = _ver_tuple(self.version)
        if self.vt < (5, 4, 0):
            raise ZabbixApiError(
                f"Zabbix {self.version} has no API tokens. 5.4 or newer is required for provisioning."
            )

    @classmethod
    def login(cls, url: str, user: str, password: str, timeout: float = 15.0):
        """Session login with user and password (test kit only; production
        provisioning uses an API token). 5.4+ uses 'username', older 'user'."""
        api = cls.__new__(cls)
        api.url = url if url.endswith("api_jsonrpc.php") else url.rstrip("/") + "/api_jsonrpc.php"
        api.timeout, api._id, api.token = timeout, 0, ""
        api.version = api._raw_call("apiinfo.version", {}, auth=False)
        api.vt = _ver_tuple(api.version)
        field = "username" if api.vt >= (5, 4, 0) else "user"
        api.token = api._raw_call("user.login", {field: user, "password": password}, auth=False)
        return api

    def _raw_call(self, method: str, params, auth: bool = True):
        self._id += 1
        body = {"jsonrpc": "2.0", "method": method, "params": params, "id": self._id}
        headers = {"Content-Type": "application/json-rpc"}
        if auth:
            if self.vt >= (6, 4, 0):
                headers["Authorization"] = f"Bearer {self.token}"
            else:
                body["auth"] = self.token
        req = urllib.request.Request(
            self.url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                resp = json.loads(r.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise ZabbixApiError(f"{method}: cannot reach {self.url}: {exc}") from exc
        if "error" in resp:
            err = resp["error"]
            raise ZabbixApiError(f"{method}: {err.get('message')} {err.get('data', '')}".strip())
        return resp["result"]

    def call(self, method: str, params):
        return self._raw_call(method, params, auth=True)

    # ------------------------------------------------------------------ helpers

    def ensure_host_group(self, name: str) -> str:
        found = self.call("hostgroup.get", {"filter": {"name": [name]}, "output": ["groupid"]})
        if found:
            return found[0]["groupid"]
        return self.call("hostgroup.create", {"name": name})["groupids"][0]

    def template_id(self, name: str) -> str:
        found = self.call("template.get", {"filter": {"host": [name]}, "output": ["templateid"]})
        if not found:
            raise ZabbixApiError(
                f"Template '{name}' not found. Import zbx_template_inspektor.yaml first."
            )
        return found[0]["templateid"]

    def ensure_host(self, host: str, group_id: str, template_id: str, ip: str,
                    description: str = "") -> tuple:
        """Returns (hostid, created: bool). Existing hosts are linked to the
        template if they are not already; nothing else is changed."""
        found = self.call("host.get", {
            "filter": {"host": [host]},
            "output": ["hostid"],
            "selectParentTemplates": ["templateid"],
        })
        if found:
            h = found[0]
            linked = {t["templateid"] for t in h.get("parentTemplates", [])}
            if template_id not in linked:
                self.call("host.massadd", {
                    "hosts": [{"hostid": h["hostid"]}],
                    "templates": [{"templateid": template_id}],
                })
            return h["hostid"], False

        params = {
            "host": host,
            "groups": [{"groupid": group_id}],
            "templates": [{"templateid": template_id}],
            "description": description,
            "macros": [{"macro": "{$INSPEKTOR.IP}", "value": ip}],
        }
        # Trapper items need no interface. The inventory field keeps the IP
        # visible to the operator.
        params["inventory_mode"] = 0
        params["inventory"] = {"alias": ip}
        res = self.call("host.create", params)
        return res["hostids"][0], True
