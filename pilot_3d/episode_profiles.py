"""Language and cast choices, independent of any examination's task numbering."""

ACTORS = ("candidate_a", "candidate_b", "examiner", "observer")
LANGUAGES = {
    "de": {
        "tts": "German",
        "alignment_model": "VOXPOPULI_ASR_BASE_10K_DE",
        "function_words": (
            "aber als am an auch auf aus bei bis das dem den der des die doch du ein eine "
            "einem einen einer es für haben ich im in ist ja können könnten mit nach nicht "
            "oder sie so um und uns von vor wäre wir zu zum zur"
        ),
        "speaker_prefix": "Es spricht: ",
        "picture_prompt": "Beschreibe das Bild.",
        "task_picture_prompt": "Bereite deine Fragen vor.",
        "experience_prompt": "Erzähle von dir.",
        "learning_pause": "Lernpause · Video anhalten.",
        "picture_prefix": "Bild · ",
        "notice_title": "Anzeige · vergrößerter Text",
        "notice_prefix": "Detail · ",
        "ai_disclosure": "KI-generierte Stimmen und animierte Figuren.",
        "rig_adaptation": (
            "Für dieses Video: Kleidung/Haare umgefärbt, Figuren skaliert, posiert und animiert. "
            "Keine Unterstützung oder Empfehlung durch Blender Foundation/Blender Studio."
        ),
    },
    "fr": {
        "tts": "French",
        "alignment_model": "VOXPOPULI_ASR_BASE_10K_FR",
        "function_words": (
            "à au aux avec ce ces cet cette dans de des du elle en et eux il ils je la le les "
            "leur lui ma mais me mes moi mon ne nos notre nous on ou par pas pour que qui sa "
            "se ses son sur ta te tes toi ton tu un une vos votre vous y est sont être avoir"
        ),
        "speaker_prefix": "Intervenant : ",
        "picture_prompt": "Décrivez l'image.",
        "task_picture_prompt": "Préparez vos questions.",
        "experience_prompt": "Parlez de votre expérience.",
        "learning_pause": "Pause · Arrêtez la vidéo.",
        "picture_prefix": "Image · ",
        "notice_title": "Annonce · texte agrandi",
        "notice_prefix": "Détail · ",
        "ai_disclosure": "Voix de synthèse et personnages animés générés avec l'IA.",
        "rig_adaptation": (
            "Pour cette vidéo : vêtements et cheveux recolorés, personnages redimensionnés, "
            "mis en pose et animés. Aucun soutien ni recommandation de Blender Foundation/Blender Studio."
        ),
    },
}


def language_code(episode):
    code = episode.get("language", "de")
    if not isinstance(code, str) or code not in LANGUAGES:
        raise ValueError("language must be de or fr; other speech/alignment languages are not implemented.")
    return code


def language_profile(episode):
    profile = LANGUAGES[language_code(episode)]
    exam = episode.get("exam", {})
    if (language_code(episode) == "fr" and isinstance(exam, dict)
            and exam.get("family") == "tef_canada" and exam.get("skill") == "speaking"
            and exam.get("section") == "B"):
        return {**profile, "task_picture_prompt": "Préparez vos arguments.",
                "notice_title": "Préparez vos arguments."}
    return profile


def scene_layout(episode):
    scene = episode.get("scene", {})
    if not isinstance(scene, dict):
        raise ValueError("scene must be an object.")
    layout = scene.get("layout", "pair")
    if layout not in ("pair", "interview"):
        raise ValueError("scene.layout must be pair or interview.")
    if "observer" in scene and type(scene["observer"]) is not bool:
        raise ValueError("scene.observer must be a boolean.")
    return layout


def active_actors(episode):
    layout = scene_layout(episode)
    observer = episode.get("scene", {}).get("observer", layout == "pair")
    return tuple(name for name in ACTORS if
                 (name != "candidate_b" or layout == "pair") and (name != "observer" or observer))


def overview_camera(episode):
    return "wide" if scene_layout(episode) == "interview" else "candidates"
