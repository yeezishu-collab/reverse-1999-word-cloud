# Data Contract

`docs/data.json` is the public dashboard payload.

```json
{
  "generated_at": "2026-04-28T00:00:00+00:00",
  "summary": {
    "documents": 3,
    "tokens": 120,
    "unique_terms": 80,
    "median_document_characters": 190,
    "window_days": 365,
    "sources": ["overview"],
    "platforms": ["sample"],
    "mode": "sample"
  },
  "top_words": [{ "text": "维尔汀", "value": 8 }],
  "by_source": {
    "overview": [{ "text": "剧情", "value": 4 }]
  },
  "by_platform": {
    "sample": [{ "text": "角色", "value": 5 }]
  },
  "by_version": {
    "3.6": {
      "id": "3.6",
      "name": "版本3.6",
      "start": "2026-04-08T21:00:00+00:00",
      "end": "2026-04-29T21:00:00+00:00",
      "documents": 1,
      "tokens": 29,
      "unique_terms": 28,
      "top_words": [{ "text": "主线剧情", "value": 2 }]
    }
  },
  "versions": [
    {
      "id": "3.6",
      "name": "版本3.6",
      "start": "2026-04-08T21:00:00+00:00",
      "end": "2026-04-29T21:00:00+00:00",
      "top_words": [{ "text": "主线剧情", "value": 2 }]
    }
  ],
  "documents": [
    {
      "source": "overview",
      "platform": "sample",
      "title": "overview",
      "characters": 200,
      "collected_at": "2026-04-28T00:00:00+00:00",
      "url": ""
    }
  ]
}
```
