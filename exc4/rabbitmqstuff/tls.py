import requests
"""
group:webdevmaniac,rabbit:czpXKQff6cjkA57R9dnaSLCBWxH6N79paBZrhEMOs2k,api:r6QFfjLwynm67hltU6k2F-kLe-8dvhM5_hSWqHtDyl4,api_server:https://86.50.230.115
"""
import ssl
import pika
"""
    "@namespaces": {
        "pwpex": {
            "name": "https://86.50.230.115/link-relations/"
        }
    },
    "@controls": {
        "profile": {
            "href": "https://86.50.230.115/profiles/"
        },
        "pwpex:certificates": {
            "title": "Certificates collection resource",
            "href": "https://86.50.230.115/api/groups/webdevmaniac/certificates/"
        },
        "collection": {
            "title": "Group collection",
            "href": "https://86.50.230.115/api/groups/"
        }
    }"""


requests.get("https://86.50.230.115", verify=False)
