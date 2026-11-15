"""Tokenisation and detection of suspicious words."""
import re

from api import fetch_ngram_data


def tokenize(text):

    segments = re.split(r'[.,:;!?()"\n]+', text)
    cleaned = []
    for segment in segments:
        if segment.strip():
            cleaned.append(segment.strip())

    for i in range(len(cleaned)):
        words = cleaned[i].split()
        if words:
            words[0] = words[0].lower()
            cleaned[i] = ' '.join(words)

    ngrams = {"unigrams" : [],
              "bigrams": []}
    for segment in cleaned:
        words = segment.split()

        for word in words:
            ngrams["unigrams"].append(word)

        if len(words) >= 2:
            for i in range(len(words) - 1):
                bigram = words[i] + ' ' + words[i + 1]
                ngrams["bigrams"].append(bigram)


    return ngrams, cleaned


def find_sus_by_segments(segments, word_map):
    # Returns, for each segment, the set of word positions that look suspicious.
    sus_by_segments = []
    for segment in segments:
        element = set()
        words = segment.split()
        for i, word in enumerate(words):
            data = fetch_ngram_data(word)
            if data and (data.get("count", 0) == None or int(data.get("count", 0)) < 100):
                element.add(i)
            else:
                if word in word_map:
                    element.add(i)
        if len(words) >= 2:
            for i in range(len(words) - 1):
                if i not in element and i + 1 not in element:
                    data = fetch_ngram_data(words[i] + ' ' + words[i + 1])
                    if data and (data.get("count", 0) == None or int(data.get("count", 0)) < 50):
                        element.add(i + 1)

        sus_by_segments.append(element)
    return sus_by_segments
