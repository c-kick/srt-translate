# Exemplars: Dual Speaker & Dialogue Formatting

Gold-standard EN→NL pairs demonstrating multi-speaker cue construction.
Sources: The Remains of the Day (1993), Fawlty Towers S01E06 (1975) — verified NL translations.

---

## Core Rule Reminder

First line: NEVER starts with dash.
Second line: starts with "-" (dash, no space after dash).

---

## Quick Exchanges Merged Into Single Cues

### Question + short answer
EN: "Have you nothing better to do than stand around?" / "Look at it and tell me the truth."
NL: "Hebt u niks beters te doen? - Bekijk die Chinees en wees eerlijk."
WHY: Two speakers, one cue. First speaker's question + second speaker's demand. Clean, fast, no wasted screen time.

### Greeting + response
EN: "Thank you, Stevens." / "Mr. Lewis."
NL: "Dank je, Stevens. - Mr. Lewis."
WHY: Minimal exchange. Both speakers acknowledged in one cue. No standalone "Mr. Lewis" cue.

### Status check + reply absorbed
EN: "Thank you. That is most kind of you." / (from preceding cue) "My condolences."
NL: "Gecondoleerd. - Dank u, dat is heel vriendelijk."
WHY: Condolence and acknowledgment in one cue. "That is most kind" → "heel vriendelijk" (condensed).

### Confirm + follow-up
EN: "Yes, thank you." / "Good." / "Would you like to know what took place?"
NL: "Ja. Wilt u weten wat er gebeurd is?"
WHY: "Good" is filler — dropped. Answer and next question flow naturally.

---

## Dialogue Scenes With Register Contrast

### Formal exchange (Stevens + Lord Darlington)
EN: "We are well prepared, my lord." / "I'm sure you are."
NL: "We zijn erop voorbereid. - Dat geloof ik."
WHY: Both lines formal. "My lord" dropped (visual context). "I'm sure you are" → "Dat geloof ik" (I believe so — formal but concise).

### Mixed register (Lord + young guest)
EN: "Die komt nooit. - Hij heeft zojuist toegezegd."
WHY: Lord speaks casually ("Die komt nooit" — blunt). Stevens's reply is measured. Register contrast in one cue shows the relationship.

### Staff banter (informal je/jij)
EN: "Burned again?" / "Yes, I'm sorry, sir."
NL: "Alweer verbrand? - Het spijt me, meneer."
WHY: Mr. Lewis (employer) uses casual question. Staff member responds with "meneer" — formal toward employer even in informal exchange.

---

## Three-Way Exchanges Handled Across Cues

### Rapid three-person scene split into dual-speaker cues
EN: "It is a small mistake." / "Your father is entrusted with more than he can cope with."
NL: "Het is een klein foutje. - Uw vader kan het werk niet aan."
WHY: Two speakers, opposing views, one cue. First line is Stevens's defense; dash-line is Miss Kenton's concern. The third participant (the father) is discussed, not speaking.

### Boss + two staff members
EN: "Mr. Stevens Sr. is very good at his job..." / "I can assure you that I'm very good at mine." / "Of course." / "Thank you." / "If you will please excuse me."
NL: "Mr. Stevens senior is vast heel goed in z'n werk." / "Ik verzeker u dat ik heel goed in het mijne ben." / "Natuurlijk. - Dank u. En nu moet ik gaan."
WHY: Five EN cues → three NL. The final NL cue is dual-speaker: Stevens's "Natuurlijk" + Miss Kenton's departure in one cue.

---

## What NOT to Merge as Dual Speaker

### Emotional beats need separate cues
EN: "Miss Kenton, you are of very great value to this house."
NL: "Miss Kenton, u bent van grote waarde voor dit huis."
WHY: This stands alone. Stevens's rare emotional statement needs its own cue for dramatic weight. Don't merge with Miss Kenton's response.

### Long lines — keep separate
If either speaker's text exceeds ~35 characters, splitting across cues is better than creating an unbalanced dual-speaker cue. Rule of thumb: dual-speaker works when both lines are short.

### Attribution must be clear
Never create a dual-speaker cue where it's unclear who says which line. If the scene has three speakers and two could plausibly say either line, use separate cues.

---

## Merge Script Output Format (Fawlty Towers S01E06)

These examples show the exact format `auto_merge_cues.py` produces from `[SC]` markers. The merge script joins two cues with `\n-` — first line has no dash, second line starts with `-` (no space after dash).

### Sentence-boundary split — two speakers, clean break
EN: "That's not blue." / "It's got blue things on it."
NL:
```
Die is niet blauw.
-Er zitten blauwe dingen op.
```
WHY: Each speaker gets one complete sentence. Clean split at the sentence boundary. First line: no dash. Second line: `-` immediately followed by text.

### Question + terse reply — comedy pacing
EN: "You still here?" / "Apparently."
NL:
```
Bent u er nog?
-Kennelijk.
```
WHY: Short question, shorter answer. The dual-speaker cue preserves comedic timing — a standalone "Kennelijk." cue would waste screen time and kill the punchline.

### Instruction + exasperated response
EN: "And will you get me my phone book, please?" / "Like I don't have enough to do."
NL:
```
Pak je m'n telefoonboek?
-Alsof ik niet genoeg te doen heb.
```
WHY: Request + complaint in one cue. Register contrast: Sybil's casual "pak je" vs Basil's sarcastic retort. Note "please" dropped — subtitling economy.

### Statement + contradiction — rapid back-and-forth
EN: "No, no dogs in here." / "I wouldn't bet on it."
NL:
```
Nee, geen honden hier.
-Dat zou ik niet zeggen.
```
WHY: Denial + undercut. The two lines play off each other — separating them would lose the comedic contrast.

### Formal register in dual-speaker (nurse + patient)
EN: "Let's sit you up a bit." / "Thank you, sister."
NL:
```
Ik help u even overeind.
-Dank u, zuster.
```
WHY: Both speakers use u — formal hospital setting. "Sister" → "zuster" (Dutch term for nurse). Register consistency even within a dual-speaker cue.

---

## Negative Examples — What NOT to Do

### WRONG: Dash on first line
```
-Wat zeg je?
-Red je het wel?
```
CORRECT:
```
Wat zeg je?
-Red je het wel?
```
WHY: First line NEVER starts with a dash. Only the second speaker gets a dash. Two dashes implies three speakers (one before the cue, two inside it).

### WRONG: Same speaker formatted as dual-speaker
```
Het is niet smerig.
-Het is prachtig.
```
CORRECT:
```
Het is niet smerig,
het is prachtig.
```
WHY: Same speaker, same sentence. The dash falsely signals a speaker change. Without `[SC]`, the merge script would join these with a space: "Het is niet smerig, het is prachtig." — which is correct.

### WRONG: Space after dash
```
Die is niet blauw.
- Er zitten blauwe dingen op.
```
CORRECT:
```
Die is niet blauw.
-Er zitten blauwe dingen op.
```
WHY: Auteursbond standard: no space after the dash. `-Text`, not `- Text`.
