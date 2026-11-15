import json
import time

from flask import Flask, render_template, request
from markupsafe import Markup, escape

from candidates import generate_corrections_with_korpus_only_sus
from detection import find_sus_by_segments, tokenize
from hmm import transition_matrix2, viterbi2

app = Flask(__name__)


def load_resources():
    with open("static/word_map.json", "r", encoding="utf-8") as f:
        word_map = json.load(f)

    warning = None
    try:
        with open("static/types.lang.utf8", "r", encoding="utf-8") as f:
            korpus = set(word.strip() for word in f if word.strip())
    except FileNotFoundError:
        korpus = set()
        warning = "Upozorenje: static/types.lang.utf8 nije pronađen, kandidati po udaljenosti uređivanja su isključeni."
    return word_map, korpus, warning


WORD_MAP, KORPUS, KORPUS_WARNING = load_resources()


@app.route("/", methods=['GET', 'POST'])
def index():
    message = None
    user_input = None
    output = None
    timing = f''

    if request.method == 'POST':
        user_input = request.form['user_input']
        mode_on = 'mode_switch' in request.form

        start1 = time.perf_counter()
        ngrams, segments = tokenize(user_input)
        end1 = time.perf_counter()
        start5 = time.perf_counter()
        sus_by_segments = find_sus_by_segments(segments, WORD_MAP)
        end5 = time.perf_counter()
        start2 = time.perf_counter()
        corr_dict2, generating_time = generate_corrections_with_korpus_only_sus(segments, sus_by_segments, WORD_MAP, KORPUS)
        end2 = time.perf_counter()
        start3 = time.perf_counter()
        transitions, transitions_time = transition_matrix2(segments, corr_dict2)
        end3 = time.perf_counter()
        start4 = time.perf_counter()
        corrected_list = viterbi2(segments, corr_dict2, transitions)
        end4 = time.perf_counter()


        if mode_on:
            message = f"{print_corrections(segments, corr_dict2)}\n\n\n{print_nested_dict(transitions)}"
            timing += f'Time\n'
            timing += f'Tokenizacija: {end1-start1}\n'
            timing += f'Detekcija sumnjivih riječi (API dohvat frekvencija): {end5-start5}\n'
            timing += f'Najdulje vrijeme generiranja za jednu riječ: {generating_time}\n'
            timing += f'Ukupno vrijeme generiranja: {end2-start2}\n'
            timing += f'Najdulje računanje tranzicija za jedan segment: {transitions_time}\n'
            timing += f'Ukupno računanje tranzicijskih vjerojatnosti: {end3-start3}\n'
            timing += f'Viterbi algoritam: {end4-start4}\n'
        output = pair_lists_to_highlighted_html(segments, corrected_list, corr_dict2)


    return render_template('index.html', message=message, user_input=user_input, output=output, timing=timing, warning=KORPUS_WARNING)


def print_corrections(segments, corrections):
    output = ""
    for segment, segment_corrections in zip(segments, corrections):
        for word, candidates in zip(segment.split(), segment_corrections):
            output += f"{word}:\n"
            for value in candidates:
                output += f"{value}\n"
            output += "\n\n"
    return output

def print_nested_dict(nested_dict):
    output = ""
    for outer_key, inner_dict in nested_dict.items():
        output += f"{outer_key}:\n"
        if isinstance(inner_dict, dict):
            for inner_key, value in inner_dict.items():
                output += f"  {inner_key}: {value}\n"
        else:
            output += f"  {inner_dict}\n"
        output += "\n"
    return output


def pair_lists_to_highlighted_html(original_list, corrected_list, corrections):
    html_output = ""

    for segment, corrected_words, segment_corrections in zip(original_list, corrected_list, corrections):
        original_words = segment.split()
        original_line = ""
        corrected_line = ""

        for orig_word, corr_word, candidates in zip(original_words, corrected_words, segment_corrections):
            if len(candidates) > 1:
                original_line += f'<span class="incorrect">{escape(orig_word)}</span> '
                corrected_line += f'<span class="corrected">{escape(corr_word)}</span> '
            else:
                original_line += f'{escape(orig_word)} '
                corrected_line += f'{escape(corr_word)} '

        html_output += f"<div class='segment-block'>"
        html_output += f"<div><strong>Originalno:</strong> {original_line.strip()}</div>"
        html_output += f"<div><strong>Ispravljeno:</strong> {corrected_line.strip()}</div>"
        html_output += f"</div><br>"

    # Every user-supplied word above went through escape(), so the result is safe to render as HTML.
    return Markup(html_output.strip())


if __name__ == "__main__":
    app.run()
