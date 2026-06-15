"""
Content Templates for AI World Cup 2026 YouTube Shorts Engine.

Defines 9 content template types, each with fully-engineered LLM prompts
that instruct Gemini to produce structured VideoScript JSON for automated
short-form video generation.
"""

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ScriptSegment:
    """A single segment of a video script."""
    narration: str          # What the TTS voice will say
    visual_cue: str         # What image/graphic to show
    duration_hint: float    # Suggested duration in seconds


@dataclass
class VideoScript:
    """Complete output produced by an LLM from a content template."""
    segments: list          # list of ScriptSegment dicts
    title: str              # YouTube title
    description: str        # YouTube description
    tags: list              # YouTube tags
    thumbnail_text: str     # Bold text for thumbnail
    content_type: str       # Template name
    topic: str              # Specific topic


@dataclass
class ContentTemplate:
    """Blueprint for one category of YouTube Shorts content."""
    name: str                    # 'match_preview', 'player_profile', etc.
    display_name: str            # 'Match Preview'
    duration_range: tuple        # (min_seconds, max_seconds)
    segment_count_range: tuple   # (min_segments, max_segments)
    system_prompt: str           # Full LLM system prompt
    user_prompt_template: str    # LLM user prompt with {placeholders}
    visual_style: str            # 'stock_footage', 'text_cards', 'mixed'
    default_pexels_queries: list # Default search terms
    title_template: str          # YouTube title format
    default_tags: list           # Default tags
    hashtags: list               # Description hashtags


# ---------------------------------------------------------------------------
# Shared JSON schema description injected into every system prompt
# ---------------------------------------------------------------------------

_JSON_OUTPUT_SCHEMA = """
You MUST return ONLY valid JSON (no markdown fences, no commentary outside the JSON).
The JSON must conform EXACTLY to this schema:

{
  "segments": [
    {
      "narration": "<string — what the TTS voice says>",
      "visual_cue": "<string — description of the image, clip, or graphic to show>",
      "duration_hint": <float — seconds this segment should last>
    }
  ],
  "title": "<string — YouTube video title, max 100 chars, with emoji>",
  "description": "<string — YouTube description, 2-4 sentences + hashtags>",
  "tags": ["<string>", "..."],
  "thumbnail_text": "<string — 2-5 bold words for the thumbnail overlay>",
  "content_type": "<string — the template name>",
  "topic": "<string — the specific topic of this video>"
}

RULES:
- Every segment.narration must be punchy, conversational, and written for spoken delivery (contractions OK, no jargon dumps).
- segment.narration MUST NOT start with repetitive transition words or phrases (e.g. "Next up", "At number X", "Moving on", "First up", "Lastly"). Go straight to the point or description.
- Keep total narration under the specified duration target.
- visual_cue should describe a concrete, searchable image or graphic (e.g. "aerial shot of a packed stadium at night", NOT "exciting visual").
- title must contain at least one emoji and be clickbait-worthy without being misleading.
- thumbnail_text must be ALL CAPS, 2-5 words, designed to stop a viewer mid-scroll.
- tags must include "World Cup 2026", "FIFA", "football", "soccer", and at least 5 topic-specific tags.
- description must end with the provided hashtags.
""".strip()


# ---------------------------------------------------------------------------
# Tone & style preamble shared across prompts
# ---------------------------------------------------------------------------

_TONE_PREAMBLE = (
    "You are a top-tier Gen-Z/millennial football content creator making viral, high-retention "
    "YouTube Shorts and TikToks about the 2026 World Cup. Your vibe is hype, charismatic, "
    "and opinionated—like a knowledgeable fan talking to their friends, not a TV presenter. "
    "Use current football/internet slang naturally (e.g., 'let him cook', 'unreal aura', 'generational', "
    "'cooked', 'clean sheets', 'coldest player', 'rent-free', 'locked in', 'absolute cinema').\n\n"
    "CRITICAL ANTI-REPETITION RULES:\n"
    "1. Hook variability: Never start with generic intros like 'Did you know', 'Welcome back', or 'Today we are looking at'. Start immediately with a bold, controversial claim, a high-stakes question, or an insane stat.\n"
    "2. No repetitive transitions: Do NOT use phrases like 'Next up', 'Moving on to', 'First up', 'At number...', 'Let's start with' at the beginning of segments. Dive straight into the subject.\n"
    "3. Natural phrasing: Write exactly how people talk on TikTok/Shorts—short punchy sentences, active verbs, and emotional reactions.\n"
    "4. Dynamic Call-To-Action (CTA): End with a fresh, punchy question or challenge, never the same generic request."
)


# ---------------------------------------------------------------------------
# Template definitions
# ---------------------------------------------------------------------------

TEMPLATES: dict[str, ContentTemplate] = {}


# ── 1. match_preview ──────────────────────────────────────────────────────

TEMPLATES["match_preview"] = ContentTemplate(
    name="match_preview",
    display_name="Match Preview",
    duration_range=(28, 45),
    segment_count_range=(4, 7),
    system_prompt=f"""{_TONE_PREAMBLE}

CONTENT TYPE: Match Preview
You are generating a pre-match analysis and prediction for an upcoming World Cup 2026 match.

STRUCTURE (4-7 segments, ~30-45 seconds total):
1. THE HOOK (2-3 s): Start with a bold, high-hype opinion or prediction that will split the comments. Avoid generic 'Team A vs Team B' intros. E.g. 'This is about to be the most chaotic match of the group stage.' or 'Everyone thinks [Team A] is cooked, but they are secretly building a masterpiece.'
2. WHAT'S AT STAKE (5-7 s): Quick, passionate breakdown of why this match is absolute cinema (group drama, elimination pressure, etc.).
3. THE KEY PLAYER BATTLE (6-10 s): Focus on 1-2 star players. E.g., striker vs keeper. Use punchy hype like 'He has been having a generational season' or 'He has unmatched aura right now.'
4. THE TACTICAL COOKING / FORM (5-8 s): Highlight recent form/stats but frame it dynamically. E.g. 'They haven't conceded a single goal in 4 games. Absolute wall.'
5. THE PREDICTION (4-6 s): Give a specific, highly-opinionated prediction with a scoreline. Make it sound bold.
6. CTA (3-4 s): Challenge the viewer with a dynamic question. E.g. 'Tell me I'm wrong in the comments—what's your scoreline prediction?'

VISUAL STYLE: Mix of stadium footage, player close-ups, team crests with VS graphic, stat overlays.

{_JSON_OUTPUT_SCHEMA}
""",
    user_prompt_template=(
        "Create a Match Preview video script for the upcoming World Cup 2026 match: "
        "{team_a} vs {team_b}.\n"
        "Match details: {match_details}\n"
        "Key players to mention: {key_players}\n"
        "Recent form: {recent_form}\n"
        "Head-to-head record: {h2h}\n"
        "Stakes: {stakes}\n\n"
        "Return ONLY the JSON."
    ),
    visual_style="mixed",
    default_pexels_queries=[
        "football stadium crowd",
        "soccer match night",
        "football players walking out tunnel",
        "soccer fans cheering",
        "world cup trophy",
    ],
    title_template="{team_a} vs {team_b} — Who WINS? 🔥 World Cup 2026 Preview",
    default_tags=[
        "World Cup 2026", "FIFA", "football", "soccer",
        "match preview", "predictions", "world cup preview",
        "football analysis", "soccer predictions",
    ],
    hashtags=[
        "#WorldCup2026", "#FIFA", "#Football", "#Soccer",
        "#MatchPreview", "#Predictions",
    ],
)


# ── 2. player_profile ─────────────────────────────────────────────────────

TEMPLATES["player_profile"] = ContentTemplate(
    name="player_profile",
    display_name="Player Profile",
    duration_range=(25, 35),
    segment_count_range=(4, 6),
    system_prompt=f"""{_TONE_PREAMBLE}

CONTENT TYPE: Player Profile (30-Second Spotlight)
You are creating a rapid-fire player spotlight that makes the viewer feel like they KNOW this player in 30 seconds.

STRUCTURE (4-6 segments, ~25-35 seconds total):
1. THE HOOK (2-3 s): Start with their most mind-blowing stat or a controversial comparison. E.g., 'He is secretly clear of every midfielder in the tournament.' or 'This player's aura is off the charts right now.'
2. THE RISE / GRIND (5-7 s): Paint their origin story or sudden breakthrough. E.g., 'He went from playing in the second division to starting at the World Cup in two years. Unreal grind.'
3. GENERATIONAL SKILLS (6-8 s): What makes them a baller. E.g. 'His dribbling is pure poetry' or 'He is an absolute wall in defense.'
4. HUMAN FACTOR / TRIVIA (4-5 s): A fun quirk, celebration, or off-pitch moment that makes them instantly memorable.
5. TOURNAMENT OUTLOOK (4-6 s): How they are going to cook at the World Cup. Set expectations high.
6. CTA (2-3 s): 'Is he cooking or is he overrated? Drop your hot takes in the comments!'

VISUAL STYLE: Player action shots, skill highlights, stat cards with bold numbers, national flag overlay.

{_JSON_OUTPUT_SCHEMA}
""",
    user_prompt_template=(
        "Create a Player Profile video script for {player_name}.\n"
        "Nationality: {nationality}\n"
        "Club: {club}\n"
        "Position: {position}\n"
        "Key stats: {stats}\n"
        "Fun facts: {fun_facts}\n"
        "World Cup 2026 role: {tournament_role}\n\n"
        "Return ONLY the JSON."
    ),
    visual_style="mixed",
    default_pexels_queries=[
        "soccer player portrait",
        "football player celebration",
        "soccer skills close up",
        "football training session",
        "national football team",
    ],
    title_template="You DON'T Know {player_name} ⚡ World Cup 2026 Star",
    default_tags=[
        "World Cup 2026", "FIFA", "football", "soccer",
        "player profile", "football stars", "best players",
        "world cup players", "football highlights",
    ],
    hashtags=[
        "#WorldCup2026", "#FIFA", "#Football", "#Soccer",
        "#PlayerProfile", "#WorldCupStars",
    ],
)


# ── 3. top_10 ─────────────────────────────────────────────────────────────

TEMPLATES["top_10"] = ContentTemplate(
    name="top_10",
    display_name="Top 10 Countdown",
    duration_range=(40, 60),
    segment_count_range=(11, 14),
    system_prompt=f"""{_TONE_PREAMBLE}

CONTENT TYPE: Top 10 Countdown
You are creating an addictive, fast-paced Top 10 countdown list (e.g., Top 10 World Cup Goals, Top 10 Saves, Top 10 Upsets).

STRUCTURE (11-14 segments, ~40-60 seconds total):
1. HOOK (2-3 s): Tease the top spots without using formulaic count-ups. E.g. 'The number one spot on this list lives rent-free in every football fan's head.' or 'You are NOT ready for what takes number one.'
2. ENTRIES #10 through #2 (3-5 s each): Each entry gets:
   - The number announcement ('Number 7!')
   - A vivid 1-2 sentence description of the moment
   - Why it's on the list
   DO NOT use repetitive transitions. Keep the pace quick and build hype.
3. THE DRAMATIC HOVER (2-3 s): Pause before revealing the top spot. 'But the coldest moment of them all...' or 'And at number one, we have...'
4. ENTRY #1 (4-6 s): The ultimate reveal. Explain why this moment has legendary status.
5. CTA (2-3 s): 'What did we miss? Tell us your list in the comments and subscribe!'

PACING RULES:
- Lower entries (#10-#6) can be rapid (3 s each).
- Middle entries (#5-#2) get slightly more detail (4-5 s each).
- #1 gets the most time and drama.
- Use transitional energy shifts: 'But wait, it gets crazier...'

VISUAL STYLE: Numbered countdown graphics, historical footage descriptions, reaction-style overlays.

{_JSON_OUTPUT_SCHEMA}
""",
    user_prompt_template=(
        "Create a Top 10 Countdown video script.\n"
        "Topic: {topic}\n"
        "Context: {context}\n"
        "Specific entries to consider (optional): {suggested_entries}\n\n"
        "Return ONLY the JSON."
    ),
    visual_style="text_cards",
    default_pexels_queries=[
        "football goal celebration",
        "soccer best moments",
        "football stadium atmosphere",
        "soccer goalkeeper save",
        "world cup celebration",
    ],
    title_template="Top 10 {topic} 🏆 You Won't Believe #1!",
    default_tags=[
        "World Cup 2026", "FIFA", "football", "soccer",
        "top 10", "countdown", "best goals", "football ranking",
        "world cup moments", "football top 10",
    ],
    hashtags=[
        "#WorldCup2026", "#FIFA", "#Football", "#Soccer",
        "#Top10", "#Countdown", "#BestGoals",
    ],
)


# ── 4. daily_recap ────────────────────────────────────────────────────────

TEMPLATES["daily_recap"] = ContentTemplate(
    name="daily_recap",
    display_name="Daily Recap",
    duration_range=(35, 55),
    segment_count_range=(5, 9),
    system_prompt=f"""{_TONE_PREAMBLE}

CONTENT TYPE: Daily Recap (Post-Matchday Summary)
You are creating a rapid-fire recap of all the day's World Cup action. Viewers who missed the games should feel they saw everything in under a minute.

STRUCTURE (5-9 segments, ~35-55 seconds total):
1. HOOK (2-3 s): Start with the wildest event of the day. E.g. 'The scriptwriters for this World Cup are absolutely cooking.' or 'Today was a historic disaster for [Team].'
2. MATCH RESULTS (4-7 s each, 2-4 matches): For each match:
   - Scoreline + brief key moment (winning goal, red card, penalty drama).
   - E.g. '[Player] decided to carry the whole team on his back' or 'It was a total masterclass.'
   Keep each match recap tight — 2-3 sentences max.
3. STANDINGS & DRAMA (4-6 s): Who's going home, who's locked in for knockouts. E.g., '[Team] is officially in trouble.'
4. STANDINGS UPDATE (3-5 s): Quick snapshot — group standing shifts.
5. TOMORROW PREVIEW TEASE (3-4 s): 'Tomorrow is going to be even more wild—we've got [Team] vs [Team]!'
6. CTA (2-3 s): 'Drop your matchday ratings below!'

VISUAL STYLE: Scoreboard graphics, highlight moment descriptions, group table overlays, flag icons.

{_JSON_OUTPUT_SCHEMA}
""",
    user_prompt_template=(
        "Create a Daily Recap video script for World Cup 2026.\n"
        "Matchday: {matchday}\n"
        "Results: {results}\n"
        "Key moments: {key_moments}\n"
        "Standout performers: {standout_performers}\n"
        "Standings impact: {standings_impact}\n"
        "Tomorrow's matches: {tomorrow_matches}\n\n"
        "Return ONLY the JSON."
    ),
    visual_style="mixed",
    default_pexels_queries=[
        "football scoreboard",
        "soccer match highlights",
        "football fans reactions",
        "soccer stadium night lights",
        "football celebration team",
    ],
    title_template="World Cup Day {matchday} RECAP 🔥 You MISSED This!",
    default_tags=[
        "World Cup 2026", "FIFA", "football", "soccer",
        "daily recap", "match highlights", "world cup results",
        "football recap", "matchday summary",
    ],
    hashtags=[
        "#WorldCup2026", "#FIFA", "#Football", "#Soccer",
        "#DailyRecap", "#Highlights", "#WorldCupRecap",
    ],
)


# ── 5. quiz ────────────────────────────────────────────────────────────────

TEMPLATES["quiz"] = ContentTemplate(
    name="quiz",
    display_name="Interactive Quiz",
    duration_range=(20, 35),
    segment_count_range=(4, 6),
    system_prompt=f"""{_TONE_PREAMBLE}

CONTENT TYPE: Interactive Quiz / Trivia
You are creating a single trivia question that hooks viewers and makes them pause to THINK before the answer is revealed.

STRUCTURE (4-6 segments, ~20-35 seconds total):
1. HOOK (2-3 s): E.g., 'Only generational football brains are getting this one.' or 'This trivia question is going to test your knowledge to the absolute limit.'
2. QUESTION (4-6 s): Present the trivia question clearly. It should be:
   - Surprising or counterintuitive in its answer.
   - About World Cup history, records, players, or rules.
   - Specific enough to be verifiable but tricky enough to stump most viewers.
   Give 3-4 multiple choice options using the letters A, B, C, D.
3. THINK PAUSE (3-5 s): 'Write down your guess right now in the comments. No cheating.'
   (visual_cue should describe a countdown timer or thinking graphic)
4. ANSWER REVEAL (4-6 s): Reveal the correct answer with high energy. E.g. 'The correct answer is... [X]! Did you actually get it?' Add a brief 1-2 sentence explanation of WHY.
5. BONUS FACT (3-4 s): A related fun fact that makes the answer even more interesting.
6. CTA (2-3 s): 'Drop your score below: did you pass or fail? Share this with a friend who thinks they know football.'

ENGAGEMENT RULES:
- The question should be hard enough that ~30% of viewers get it wrong.
- Always encourage commenting before the reveal to boost engagement.
- WARNING: The thumbnail_text MUST NOT contain the correct answer or spoil the trivia question. Make it a hook that creates curiosity (e.g. "IMPOSSIBLE QUIZ!", "99% WILL FAIL!", "CAN YOU GUESS?").
- CRITICAL TRIVIA INTEGRITY RULES:
1. You MUST read the question EXACTLY as provided in the 'Question' field of the user prompt.
2. You MUST read the options EXACTLY as provided in the 'Options' list of the user prompt, in the EXACT order they are given, using the letters A, B, C, D. Do NOT substitute, reorder, delete, or rename any options. (e.g. if the options are Germany, Japan, Russia, Spain, you must speak them in that order: A is Germany, B is Japan, C is Russia, D is Spain).
3. You MUST reveal the correct answer EXACTLY as provided in the 'Answer' field of the user prompt.
4. You MUST base your reveal explanation on the 'Detail' field of the user prompt.
Any reordering or modification of options or correct answer will cause a mismatch with the on-screen overlays and fail the video generation.

VISUAL STYLE: Bold question text on screen, multiple choice options graphic, timer countdown, checkmark/X reveal animation.

{_JSON_OUTPUT_SCHEMA}
""",
    user_prompt_template=(
        "Create an Interactive Quiz video script.\n"
        "Quiz topic: {topic}\n"
        "Difficulty: {difficulty}\n"
        "Specific question (optional): {specific_question}\n"
        "Related facts to draw from: {related_facts}\n\n"
        "Return ONLY the JSON."
    ),
    visual_style="text_cards",
    default_pexels_queries=[
        "question mark neon",
        "quiz show lights",
        "thinking person",
        "football trivia",
        "soccer quiz",
    ],
    title_template="Can You Answer This World Cup Question? 🧠⚽",
    default_tags=[
        "World Cup 2026", "FIFA", "football", "soccer",
        "football quiz", "soccer trivia", "world cup trivia",
        "football facts", "test your knowledge",
    ],
    hashtags=[
        "#WorldCup2026", "#FIFA", "#Football", "#Soccer",
        "#Quiz", "#Trivia", "#FootballQuiz",
    ],
)


# ── 6. history ─────────────────────────────────────────────────────────────

TEMPLATES["history"] = ContentTemplate(
    name="history",
    display_name="This Day in World Cup History",
    duration_range=(28, 45),
    segment_count_range=(4, 7),
    system_prompt=f"""{_TONE_PREAMBLE}

CONTENT TYPE: This Day in World Cup History
You are a master storyteller retelling a legendary World Cup moment. Make the viewer feel like they were THERE.

STRUCTURE (4-7 segments, ~28-45 seconds total):
1. HOOK (2-3 s): Drop the viewer straight into the action with urgency. E.g. 'On this day in [Year], [Player] did something so illegal it broke the internet.' or 'This is the wildest moment in World Cup history.'
2. SETUP (5-8 s): Paint the scene — the context, the stakes. What was on the line?
3. THE MOMENT (8-12 s): Describe the key event in vivid, cinematic detail. Use present tense for immediacy: 'He picks up the ball, dribbles past one, two, three defenders...' Build suspense, then deliver.
4. AFTERMATH / IMPACT (5-7 s): What happened next? Legacy forged, rules changed, or records broken.
5. MODERN CONNECTION (3-5 s): Tie it to World Cup 2026. 'Could we see someone replicate this madness in 2026?'
6. CTA (2-3 s): 'Drop your favorite retro football moment in the comments!'

STORYTELLING RULES:
- Use sensory language — sights, sounds, crowd roars.
- Name specific players, stadiums, scorelines.
- Make it feel like a mini-documentary, not a Wikipedia summary.
- Build emotional crescendo toward the key moment.

VISUAL STYLE: Vintage-style footage descriptions, sepia/retro filters, historical photos, modern comparison shots.

{_JSON_OUTPUT_SCHEMA}
""",
    user_prompt_template=(
        "Create a 'This Day in World Cup History' video script.\n"
        "Date: {date}\n"
        "Historical event: {event}\n"
        "Key figures: {key_figures}\n"
        "Tournament context: {tournament_context}\n"
        "Legacy/impact: {legacy}\n\n"
        "Return ONLY the JSON."
    ),
    visual_style="stock_footage",
    default_pexels_queries=[
        "vintage football",
        "old soccer stadium",
        "retro sports photography",
        "football history",
        "classic soccer match",
    ],
    title_template="The Day That CHANGED Football Forever ⚽ {event_short}",
    default_tags=[
        "World Cup 2026", "FIFA", "football", "soccer",
        "football history", "world cup history", "this day in history",
        "legendary moments", "classic football",
    ],
    hashtags=[
        "#WorldCup2026", "#FIFA", "#Football", "#Soccer",
        "#FootballHistory", "#OnThisDay", "#WorldCupHistory",
    ],
)


# ── 7. squad_guide ─────────────────────────────────────────────────────────

TEMPLATES["squad_guide"] = ContentTemplate(
    name="squad_guide",
    display_name="Squad Guide",
    duration_range=(30, 50),
    segment_count_range=(5, 8),
    system_prompt=f"""{_TONE_PREAMBLE}

CONTENT TYPE: Squad Guide (Country Team Introduction)
You are introducing a World Cup 2026 squad to viewers who may not follow that country's league. Make them care about this team in under a minute.

STRUCTURE (5-8 segments, ~30-50 seconds total):
1. HOOK (2-3 s): One bold statement about this team. E.g. 'Everyone is sleeping on [Country], but their tactical setup is insane.' or 'This is why [Country] might be the ultimate dark horse in 2026.'
2. TEAM IDENTITY (5-7 s): Playing style, formation, philosophy. Use a vivid analogy (e.g. 'They play like a swarm of bees, pressing relentlessly').
3. STAR PLAYER (5-7 s): Spotlight the talisman — name, club, what makes them special, key stat.
4. KEY PLAYERS (6-8 s): Rapid-fire 2-3 other names. Mention their specific superpowers.
5. STRENGTHS (4-5 s): What this team does brilliantly. Be specific.
6. WEAKNESSES (3-4 s): Be honest — where can they be exploited? Adds credibility.
7. TOURNAMENT PREDICTION (4-5 s): How far will they go? Make a bold prediction.
8. CTA (2-3 s): 'Can they actually win it? Let me know in the comments!'

VISUAL STYLE: National flag backgrounds, player portraits with name/number overlays, formation diagrams, kit designs.

{_JSON_OUTPUT_SCHEMA}
""",
    user_prompt_template=(
        "Create a Squad Guide video script for {country} at World Cup 2026.\n"
        "Manager: {manager}\n"
        "Playing style: {playing_style}\n"
        "Star player: {star_player}\n"
        "Key players: {key_players}\n"
        "Group: {group}\n"
        "Group opponents: {group_opponents}\n"
        "FIFA ranking: {fifa_ranking}\n"
        "Qualification record: {qualification_record}\n"
        "Strengths: {strengths}\n"
        "Weaknesses: {weaknesses}\n\n"
        "Return ONLY the JSON."
    ),
    visual_style="mixed",
    default_pexels_queries=[
        "national football team",
        "soccer team lineup",
        "football players national anthem",
        "country flag stadium",
        "soccer team celebration",
    ],
    title_template="{country} World Cup 2026 Squad GUIDE 🏆 Can They Win It?",
    default_tags=[
        "World Cup 2026", "FIFA", "football", "soccer",
        "squad guide", "team preview", "world cup squads",
        "football analysis", "world cup teams",
    ],
    hashtags=[
        "#WorldCup2026", "#FIFA", "#Football", "#Soccer",
        "#SquadGuide", "#TeamPreview",
    ],
)


# ── 8. controversy ─────────────────────────────────────────────────────────

TEMPLATES["controversy"] = ContentTemplate(
    name="controversy",
    display_name="Controversial Moment",
    duration_range=(30, 50),
    segment_count_range=(5, 8),
    system_prompt=f"""{_TONE_PREAMBLE}

CONTENT TYPE: Controversial / Dramatic Moment Retelling
You are retelling a dramatic, controversial, or shocking World Cup moment in a cinematic, edge-of-your-seat storytelling style. Think true-crime documentary meets sports commentary.

STRUCTURE (5-8 segments, ~30-50 seconds total):
1. HOOK (2-3 s): E.g. 'This referee decision still lives rent-free in the mind of every [Country] fan.' or 'What happened in this match was absolute robbery.'
2. THE BUILDUP (5-7 s): Set the stage. What was happening before the controversy? Make us care about the stakes.
3. THE INCIDENT (8-12 s): Describe the controversial moment in dramatic detail. Use short, punchy sentences. E.g. 'The ball crosses the line. Or does it? The referee waves play on. Absolute chaos.'
4. THE REACTION (4-6 s): Immediately after — player fury, manager meltdowns, cards.
5. THE FALLOUT (4-6 s): Long-term consequences — rule changes, investigations, career impacts.
6. THE DEBATE (3-4 s): Present both sides. Was it the right call? Would VAR have saved them?
7. CTA (2-3 s): 'Was it a robbery or the right call? You be the ref and comment below.'

STORYTELLING RULES:
- Build tension with pacing — short sentences when drama peaks.
- Use cliffhanger moments between segments.
- Stay balanced but don't be boring — lean into the drama.
- Reference similar modern situations for relatability.

VISUAL STYLE: Dramatic lighting, slow-motion moment descriptions, split-screen debate graphics, referee close-ups.

{_JSON_OUTPUT_SCHEMA}
""",
    user_prompt_template=(
        "Create a Controversial Moment video script.\n"
        "Event: {event}\n"
        "Match: {match}\n"
        "Tournament: {tournament}\n"
        "Key figures involved: {key_figures}\n"
        "What happened: {what_happened}\n"
        "Why it was controversial: {controversy_reason}\n"
        "Aftermath/consequences: {aftermath}\n\n"
        "Return ONLY the JSON."
    ),
    visual_style="stock_footage",
    default_pexels_queries=[
        "football referee decision",
        "soccer argument referee",
        "dramatic football moment",
        "angry football fans",
        "football var screen",
    ],
    title_template="The Most CONTROVERSIAL Moment in World Cup History 😱 {event_short}",
    default_tags=[
        "World Cup 2026", "FIFA", "football", "soccer",
        "controversy", "VAR", "football drama", "shocking moments",
        "world cup drama", "referee decisions",
    ],
    hashtags=[
        "#WorldCup2026", "#FIFA", "#Football", "#Soccer",
        "#Controversy", "#Drama", "#VAR", "#FootballDrama",
    ],
)


# ── 9. facts ──────────────────────────────────────────────────────────────

TEMPLATES["facts"] = ContentTemplate(
    name="facts",
    display_name="Quick Football Fact",
    duration_range=(18, 30),
    segment_count_range=(3, 5),
    system_prompt=f"""{_TONE_PREAMBLE}

CONTENT TYPE: Quick Football Fact / Rule Explained
You are sharing a single fascinating football fact, obscure rule, or mind-blowing statistic. Educational BUT entertaining — think "I can't believe I didn't know that!" energy.

STRUCTURE (3-5 segments, ~18-30 seconds total):
1. HOOK (2-3 s): E.g. 'This football fact is going to break your brain.' or '99% of fans don't know this hidden rule.'
2. THE FACT (6-10 s): Deliver the fact/rule with clarity and enthusiasm. Keep it simple and use analogies.
3. CONTEXT / WHY IT MATTERS (4-6 s): Connect it to the bigger picture. Why is this detail legendary or ridiculous?
4. WORLD CUP 2026 TIE-IN (3-5 s): Relate it to the current tournament. E.g. 'Keep an eye out for this happening in 2026!'
5. CTA (2-3 s): 'Did you know this? Subscribe for more daily facts!'

TONE RULES:
- Sound genuinely amazed — this fact blew YOUR mind too.
- Avoid dry, textbook explanations. Make it feel like gossip, not a lecture.
- Use analogies to make numbers relatable: "That's like scoring a goal every 12 minutes for an entire season."

VISUAL STYLE: Bold text overlays with key numbers, infographic-style graphics, side-by-side comparisons.

{_JSON_OUTPUT_SCHEMA}
""",
    user_prompt_template=(
        "Create a Quick Football Fact video script.\n"
        "Fact/rule/stat: {topic}\n"
        "Category: {category}\n"
        "Supporting details: {details}\n"
        "World Cup 2026 connection (if any): {wc_connection}\n\n"
        "Return ONLY the JSON."
    ),
    visual_style="text_cards",
    default_pexels_queries=[
        "football infographic",
        "soccer statistics",
        "football fact",
        "soccer ball close up",
        "football field aerial",
    ],
    title_template="You DIDN'T Know This About Football ⚽🤯 {fact_short}",
    default_tags=[
        "World Cup 2026", "FIFA", "football", "soccer",
        "football facts", "soccer facts", "did you know",
        "football rules", "sports trivia",
    ],
    hashtags=[
        "#WorldCup2026", "#FIFA", "#Football", "#Soccer",
        "#FootballFacts", "#DidYouKnow", "#SoccerFacts",
    ],
)


# ── 10. breaking_news ──────────────────────────────────────────────────────

TEMPLATES["breaking_news"] = ContentTemplate(
    name="breaking_news",
    display_name="Breaking News / Trend",
    duration_range=(25, 45),
    segment_count_range=(4, 7),
    system_prompt=f"""{_TONE_PREAMBLE}

CONTENT TYPE: Breaking News & Trending Drama
You are generating a rapid-fire news script about a recent breaking story, match result, controversy, or drama at the World Cup 2026.

STRUCTURE (4-7 segments, ~25-45 seconds total):
1. HOOK (2-3 s): E.g. 'We have absolute drama breaking at the World Cup.' or 'BREAKING: Things just got chaotic in Group [Group].'
2. THE NEWS (8-12 s): Explain the core event/story clearly. What happened? Who is involved?
3. CONTEXT & REACTIONS (8-12 s): Why is this a big deal? What are fans, coaches, or other players saying?
4. IMPACT / NEXT STEPS (6-8 s): How does this affect their group standings, upcoming matches, or tournament chances?
5. Prediction/Take (4-5 s): Give a quick, opinionated take on it. Who is in the right/wrong?
6. CTA (2-3 s): 'Who is to blame for this? Let me know in the comments!'

VISUAL STYLE: News studio background, player reaction shots, social media tweet screenshots, training footage.

{_JSON_OUTPUT_SCHEMA}
""",
    user_prompt_template=(
        "Create a Breaking News video script for the trending topic:\n"
        "Headline: {headline}\n"
        "Summary: {summary}\n"
        "Related players/teams to mention: {entities}\n\n"
        "Return ONLY the JSON."
    ),
    visual_style="mixed",
    default_pexels_queries=[
        "news broadcast reporter",
        "football fans cheering phone",
        "angry soccer coach referee",
        "soccer match night action",
        "stadium floodlights",
    ],
    title_template="BREAKING: {headline} 😱 World Cup 2026 News",
    default_tags=[
        "World Cup 2026", "FIFA", "football", "soccer",
        "breaking news", "football drama", "world cup news",
        "trending football", "soccer drama",
    ],
    hashtags=[
        "#WorldCup2026", "#FIFA", "#Football", "#Soccer",
        "#BreakingNews", "#FootballDrama", "#WorldCupNews",
    ],
)


# ── 11. youtube_inspiration ────────────────────────────────────────────────

TEMPLATES["youtube_inspiration"] = ContentTemplate(
    name="youtube_inspiration",
    display_name="YouTube Inspiration",
    duration_range=(25, 45),
    segment_count_range=(4, 7),
    system_prompt=f"""{_TONE_PREAMBLE}

CONTENT TYPE: YouTube Studio Inspiration Video
You are generating a video script based on a high-demand search gap or inspiration idea provided directly by YouTube Studio.

STRUCTURE (4-7 segments, ~25-45 seconds total):
1. HOOK (2-3 s): Start with an extremely high-impact hook related directly to the topic, making the viewer want to keep watching. E.g. challenge standard opinions or present an eye-opening detail.
2. EXPLANATION / CORE DETAIL (15-25 s): Provide the core information, backstory, stats, or arguments about the topic. Be factual, exciting, and brief.
3. ENGAGEMENT / OUTLOOK (5-8 s): Discuss why this is important for the upcoming World Cup, or how it affects players/fans/history.
4. CTA (3-4 s): Prompt the user to subscribe, comment predictions, or drop their hot takes.

VISUAL STYLE: Dynamic sports imagery, player cutouts, stadium action, map animations, or custom text cards as needed.

{_JSON_OUTPUT_SCHEMA}
""",
    user_prompt_template=(
        "Create an engaging video script for this YouTube Inspiration topic: {idea}.\n"
        "Provide accurate details, interesting facts, and high-energy narration about this topic.\n\n"
        "Return ONLY the JSON."
    ),
    visual_style="mixed",
    default_pexels_queries=[
        "soccer match highlight",
        "football stadium epic shot",
        "soccer player celebrating goal",
        "world cup trophy fan excitement",
    ],
    title_template="{idea} 🔥 World Cup 2026",
    default_tags=[
        "World Cup 2026", "FIFA", "football", "soccer",
        "football analysis", "trending soccer", "world cup history",
    ],
    hashtags=[
        "#WorldCup2026", "#FIFA", "#Football", "#Soccer",
        "#Trending", "#Inspiration",
    ],
)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def get_template(name: str) -> ContentTemplate:
    """Return a single ContentTemplate by its name key.

    Args:
        name: Template name (e.g. 'match_preview', 'quiz').

    Returns:
        The matching ContentTemplate.

    Raises:
        KeyError: If no template with *name* exists.
    """
    if name not in TEMPLATES:
        available = ", ".join(sorted(TEMPLATES.keys()))
        raise KeyError(
            f"Unknown template '{name}'. Available templates: {available}"
        )
    return TEMPLATES[name]


def get_all_templates() -> list[ContentTemplate]:
    """Return a list of every registered ContentTemplate."""
    return list(TEMPLATES.values())


def get_active_templates(active_names: list[str]) -> list[ContentTemplate]:
    """Return only the templates whose names appear in *active_names*.

    Args:
        active_names: List of template name strings to include.

    Returns:
        List of matching ContentTemplate objects (order follows *active_names*).

    Raises:
        KeyError: If any name in *active_names* is not a valid template.
    """
    templates = []
    for name in active_names:
        templates.append(get_template(name))
    return templates
