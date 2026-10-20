"""Payload shapes copied from the AVEVA package (test_protocols.py and the dump scripts).
Shared by the unit tests and test/validate_template.py."""


PN_STATION = {
    "id": 1,
    "general": {"name": "vipa4-1", "ip4s": ["192.168.4.10"], "mac": "aa:bb:cc:00:00:01",
                "status": (1 << 11), "portCount": 2},
    "lastmin": {"pn_diagnosis": {"counter": {"frame_gaps": 0, "frame_overtake": 0, "breakdown": 0,
                                             "restart": 0, "alarm_high": 1, "alarm_low": 0},
                                 "jitter": {"min": -120, "max": 640}},
                "diagnosis": {"netload_in": {"average": 250000, "max": 1_250_000},
                              "netload_out": {"average": 180000, "max": 625_000}}},
    "history_all": {"pn_diagnosis": {"counter": {"frame_gaps": 12, "frame_overtake": 1, "breakdown": 2,
                                                 "restart": 2, "alarm_high": 4, "alarm_low": 1},
                                     "jitter": {"min": -1000, "max": 1000}}},
}

EIP_STATION = {
    "id": 1,
    "general": {"alias": "", "ip4s": ["192.168.1.5"], "mac": "00:20:D5:01:64:92", "status": 729},
    "rawStations": [{"isCipStation": True, "srcMac": "00:20:D5:01:64:92"}],
    "lastMin": {"counters": {"errorFramesRecv": 0, "errorFramesSend": 0},
                "diagnosis": {"netloadIn": {"average": 17719, "max": 18194},
                              "netloadOut": {"average": 11312, "max": 11813}},
                "etherNetIpDiagnosis": {"counter": {"breakdown": 0, "frameGaps": 1, "frameOvertake": 0, "restart": 0},
                                        "cycleTime": {"average": 49847}, "jitter": {"min": -15, "max": 7}}},
    "history": {"counters": {"errorFramesRecv": 0, "errorFramesSend": 1},
                "etherNetIpDiagnosis": {"counter": {"breakdown": 0, "frameGaps": 956, "frameOvertake": 0, "restart": 0},
                                        "jitter": {"min": -15, "max": 8}}},
}


def pb(addr, out_hist=0, out_last=0, status=0, name="", frames_in=405000):
    return {"id": addr,
            "general": {"status": status, "name": name},
            "history": {"frames_out": out_hist, "frames_in": frames_in, "breakdown": 1,
                        "error_frames": 40, "frame_repeat": 60, "max_frame_repeat": 4,
                        "diag_intern": 3, "diag_extern": 6, "unanswered_slave_diag": 1, "restart": 1},
            "lastmin": {"frames_out": out_last}}


