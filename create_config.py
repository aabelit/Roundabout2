import json

config = {
    "vendors": {
        "huawei": {
            "source_dir": "/home/roundabout/source/HWI",
            "file_pattern": r"A(\d{8})\.(\d{4}\+\d{4})-(\d{4}\+\d{4})_.*\.xml\.gz"
        },
        "nokia": {
            "source_dir": "/home/roundabout/source/NSN",
            "file_pattern": r"PM(\d{8})(\d{4}\+\d{4}).*\.xml\.gz",
            "systems": {
                "MO4": {
                    "source_dir": "/home/roundabout/source/NSN/MO4"
                },
                "MO5": {
                    "source_dir": "/home/roundabout/source/NSN/MO5"
                }
            }
        }
    }
}

with open("/home/roundabout2/config.json", "w") as f:
    json.dump(config, f, indent=4)

print("Config written successfully")
