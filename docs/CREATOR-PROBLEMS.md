> Imported unchanged from `sigmora-platform/docs/meta-hackathon/CREATOR-PROBLEMS.md` on 2026-10-20 (pre-event design). Where file paths or the Oct 14 model choices differ, [ARCHITECTURE.md](ARCHITECTURE.md) and [MAXXING.md](MAXXING.md) take precedence: this repo is standalone, and it adds Muse Voice Transcribe and an optional Muse Wonder escalation.

# Creator problems Safe Cut solves (evidence) + what to add to Sigmora

Researched 2026-10-14. Every claim links to a source. The Reddit pass was done the same day (section below).

## Top pain points (severity × frequency)

1. **Filming strangers covertly, then bans.** A BBC investigation found dozens of male influencers filming women with Ray-Ban Metas. "Dilara" appeared in a 1.3M-view clip showing her phone number. TikTok removed 4 channels and YouTube 2 accounts ([NatLawReview](https://natlawreview.com/article/smart-glasses-and-privacy-wearable-surveillance-and-disclosure-issues), [Digital Trends](https://www.digitaltrends.com/wearables/the-privacy-nightmare-of-smart-glasses-turns-real-as-victim-filmed-and-extorted/)). In July 2026 Instagram said it will take down "pickup" videos filmed with the glasses. Smart-glasses shipments hit 2.25M in Q1 2026, up 167%, with Meta at 69% share ([Fortune](https://fortune.com/2026/07/28/ray-ban-meta-pervert-glasses-secret-videos-women/), [CBS](https://www.cbsnews.com/news/meta-ai-smart-glasses-covert-filming-privacy/)).
2. **Privacy complaints and takedowns.** YouTube may give the uploader time to trim or blur, won't accept making the video private as a fix, and "will suspend accounts that violate people's privacy" ([YouTube](https://support.google.com/youtube/answer/7671399?hl=en)). The window is reportedly 48 hours ([Right To Be](https://hateandhope.righttobe.org/pages/youtube-safety-guide)).
3. **IRL and street formats: bans and prosecutions.** Kick's 2026 guidelines single out "bystanders filmed without consent" ([Sirency](https://www.sirency.com/blog/kick-community-guidelines-explained)). Mexican Andy was banned from Kick in August 2026 ([Dexerto](https://www.dexerto.com/entertainment/mexican-andy-banned-from-kick-after-allegedly-harassing-women-in-japan-3403788/)). Johnny Somali was sentenced to 6 months in Seoul ([Fox LA](https://www.foxla.com/news/johnny-somali-sentenced-south-korea-prison)).
4. **Legal exposure.**
   - In Buivids (CJEU C-345/17), posting identifiable people to YouTube was ruled not "household" use ([FRA](https://fra.europa.eu/en/caselaw-reference/cjeu-case-c-34517-judgment)).
   - Kenya's ODPC fined Casa Vera Lounge KSh 1.85M for posting a patron's image ([The Star](https://the-star.co.ke/news/realtime/2023-09-27-clubs-take-action-after-casa-vera-was-hit-with-sh18m-fine)).
   - US advertising needs releases from identifiable passers-by ([GFR Law](https://gfrlaw.com/what-we-do/insights/get-consent-passersby-using-their-images-advertisements)).
5. **Children.**
   - Illinois, California and Minnesota child-influencer laws; Minnesota adds a deletion right from age 13 ([Reed Smith](https://www.reedsmith.com/articles/illinois-law-closes-gap-for-child-influencers/), [Davis+Gilbert](https://www.dglaw.com/new-laws-protecting-child-influencers-what-marketers-and-influencers-need-to-know/)).
   - France gives children a right to removal ([LoC](https://www.loc.gov/item/global-legal-monitor/2020-10-30/france-parliament-adopts-law-to-protect-child-influencers-on-social-media/)).
   - Police warn that school and street signs in kids' footage reveal where they are ([CBS42](https://www.cbs42.com/news/national/police-warn-back-to-school-photos-have-hidden-clues-for-predators-what-to-check-for/)).
6. **Manual masking is slow and current tools fail.**
   - Manual redaction takes about 5–10 h per hour of footage, or about 30 min for a 1-min clip with two moving faces ([Fora Soft](https://www.forasoft.com/blog/article/video-redaction-software), a vendor source).
   - YouTube's blur misses small or far faces and flickers ([vidIQ](https://vidiq.com/blog/post/youtube-blur-tool/)).
   - CapCut's face mosaic catches "all faces" with no exclusions ([Filmora](https://filmora.wondershare.com/ai-efficiency/how-to-blur-face-in-capcut.html)).
7. **Documents, screens and personal items.** A UK estate agency's virtual tours showed unblurred financial documents and family photos, and the agency pulled all its tours ([The Negotiator](https://thenegotiator.co.uk/news/virtual-tours-privacy-bbc-property/)).
8. **Plates, location leaks, background music.**
   - Sharing dashcam footage with plates falls under GDPR; NL and MT require blurring ([Legal Documents UK](https://www.legaldocuments.co.uk/road-traffic-law/dash-cams-and-the-law/)).
   - Streamlabs tells IRL streamers to keep street signs, buildings, plates and reflections out of frame ([Streamlabs](https://streamlabs.com/content-hub/post/how-to-protect-information-while-live-streaming)).
   - Content ID claims hit background music in shops ([Social Media Today](https://www.socialmediatoday.com/news/youtube-updates-content-id-claim-policies-to-better-protect-creators/561048/)).

## Stories for the pitch

1. **Dilara (BBC, 2026):** secretly filmed on her lunch break, 1.3M views, her phone number on screen. Safe Cut catches the face AND the number before publishing. *(Primary hook.)*
2. **Louisa Melcher:** a joking street-interview answer went to 25M+ views, the interviewer mocked her removal requests, and she started a Change.org petition on 2026-08-29 ([Change.org](https://www.change.org/p/demand-tiktok-and-instagram-let-people-remove-street-interviews-they-never-consented-to)). The claims are hers and unverified; say "reported". Shows that *participants* need consent too, so it motivates the consent feature.
3. **Backup with a Kenyan link:** the Casa Vera KSh 1.85M ODPC fine.
4. **Use with care, or not at all, in front of Meta judges:** in Feb 2026, Swedish press reported that Sama annotators in Nairobi saw unblurred Ray-Ban footage, and the contract ended ([Help Net Security](https://www.helpnetsecurity.com/2026/03/05/meta-ray-ban-smart-glasses-privacy-risks/), [TNW](https://thenextweb.com/news/meta-smart-glasses-sama-kenya-workers)). If it's used at all, frame it as "privacy must be context-aware and human-approved", never as a jab.

## Personas

1. **POV, IRL and street creators**: smart-glasses users, street interviewers, travel vloggers. Meta-native, high frequency, highest takedown risk. *(Demo persona.)*
2. **Marketing teams, agencies and property videographers**: Sigmora's core market. Commercial use needs releases and an audit trail; they pay.
3. **Journalists, NGOs and citizen reporters**: protecting protesters and witnesses ([Poynter](https://www.poynter.org/ethics-trust/2020/should-journalists-show-protesters-faces/)).

Secondary: family creators (child-influencer laws), dashcam and cycling channels (plates).

## Features to add to Sigmora

| # | Feature | Scope | Effort | Meta model |
|---|---|---|---|---|
| 1 | **Context-aware people redaction**: participant vs bystander, children hidden by default, one tap to keep | **Hackathon core** | M | Muse Spark + SAM 3.1 |
| 2 | **Text and screen PII**: plates, screens, documents, house numbers, street and school signs, read and judged by content | **Hackathon core** | S–M | Muse Spark + SAM 3.1 |
| 3 | **Privacy receipt**: what was hidden, why, when, and who approved; doubles as evidence when answering a complaint | **Hackathon core** | S | Muse Spark |
| 4 | **Location scrub**: strip EXIF/GPS on export, flag landmark + address combinations | Hackathon stretch | S | Muse Spark |
| 5 | **Spoken PII**: names, numbers or addresses said aloud. Sigmora already bleeps via Scribe entity detection (`redact-sensitive.ts`); Muse Voice Transcribe has turn-level timestamps only, so keep Scribe for word timing and add Muse Spark for the judgement | Post | M | Muse Spark (+ existing Scribe) |
| 6 | **Consent capture**: QR release on location, linked to the person and clip; signed participants auto-kept clear | Post (strong for agencies) | M | Muse Spark |
| 7 | **Logo and trademark blur** for sponsor conflicts | Post | S | SAM 3.1 ("logo") + Muse Spark |
| 8 | **Live delay redaction** for IRL streams | Post (big but heavy) | L | SAM 3.1 + Muse Spark |

Skip: background-music replacement (needs audio fingerprinting, no Meta model) and likeness/deepfake detection (YouTube already ships it).

**Wording rule:** never "face recognition". Safe Cut does no identity matching. It judges roles from behaviour and context. Civil-liberties groups are actively fighting face recognition in glasses ([Markey letter](https://www.markey.senate.gov/imo/media/doc/letter_to_meta_on_frt_in_smart_glasses1.pdf)).

## Reddit pass (2026-10-14)

Method: Google `site:reddit.com` searches. Reddit itself blocks our browser tooling, so these are thread titles and Google's snippets with subreddit, comment count and age as shown on 2026-10-14. Search each title to open the thread. Quotes are the posters' words as Google showed them.

**People asking for exactly this product**
- r/finalcutpro, "Is there a fcp plugin that blurs all faces automatically?" (3 y): *"I want to do a respectful travel vlog that blurs every persons face walking by (and then unblur the few who agree to be filmed)."* That is Safe Cut's default-deny + keep-participants model, described by a creator.
- r/davinciresolve, "Is there any way to batch blur everyone's faces?" (2 y): *"To do this manually will take months."*
- r/PartneredYoutube, "Should we edit a child and bystanders out of an upcoming…" (1 mo): a cast member's 9-year-old in the background; *"Should we blur his face when he's in the background…"*
- r/UTEST, "Blurring sensitive info in videos — Nightmare job?" (2 y, 25 answers): screen-recording testers who spend ages blurring PII. Adjacent segment: screen recordings.

**Takedowns and complaints (the cost of getting it wrong)**
- r/PartneredYoutube, "Video taken down due to privacy complaint" (5 mo): *"I blurred the people's faces 100% of the video but still the privacy complaint was upheld by youtube and they took it down."* → **Face blur alone isn't enough.** People are identifiable by body, clothing, voice and context.
- r/Amazon_Influencer, "The video discloses personal/private information…" (3 y): a plate *"partially covered… frame by frame"* still got flagged. → **Partial or leaky coverage fails review.**
- r/PartneredYoutube, "Person commented on my video saying there faces…" (1 y, 80+ comments): a theme-park creator asked to delete a video because a viewer's face appears.
- r/SmallYTChannel, "YouTube Privacy Complaint Against My Entire Channel" (1 mo).
- r/PartneredYoutube, "Privacy Complaint" (2 mo): *"He said 'don't put me in the video'… You put him in the video anyway."* Consent is about being in it at all, not just the face.
- r/videos, "YouTube demand Brendan Kavanagh blur out faces on his…" (2 y, 1.9K comments): a big piano-in-public channel forced to blur bystanders. The best-known public example.

**The public's side (demand from the people being filmed)**
- r/Vent, "I hate how being recorded in public has become normal…" (4 mo, 430+); r/whatdoIdo, "I got posted on TikTok by some stranger…" (9 mo, 320+); r/melbourne, a woman filmed for a 57M-view TikTok who felt "dehumanised" (4 y, 480+).
- r/RaybanMeta, "Tyler the Creator says no to filming by dude using metas" (5 days ago, 150+): *"he… assumed consent."* Current and Meta-specific.
- r/cybersecurity, "Workers report watching Ray-Ban Meta-shot footage…" (7 mo, 60+).
- r/thepassportbros, "Philippines introduces new law you can not YouTube…" (1 y, 110+): vloggers must blur bystanders who object. Check the actual law before citing it.
- r/AskWomenOver30, "I reported a Mommy Vlogger" (3 y, 130+): a school concert video showing the school's name. Location leak via signage, which feature 4 (location scrub) covers.

**Competitors surfaced (be accurate in the pitch)**
- Small on-device apps already let you **pick faces by hand**: "PrivacyVideo" (r/VideoEditors, 3 mo: *"blurs all faces, but you can choose which ones"*), "Blurize" (r/AppsWithoutSub, 3 mo, 140+: *"shows each person as…"*), DeepMask, PutMask, ForEffect, BlurMe (plates).
- r/LivestreamFail, "Made an AI that stops streamers from leaking their address/DMs" (10 mo, 100+): screen/DM leaks on stream.
- **So the pitch must not say "nobody lets you choose."** It says: they make *you* find and pick every person, frame-check it yourself, and they cover faces only. Safe Cut **decides roles from context**, covers **plates, screens, documents and whole people**, **audits its own output for leaks**, and **publishes**.

**Design changes from this pass** (folded into DESIGN.md)
1. **Whole-person redaction** for bystanders who are prominent or close to the camera: a SAM `person` mask, not just `face`, because complaints get upheld even with 100% face blur.
2. **Zero-leak coverage is the bar.** A partly covered plate failed review, which validates the leak guard and the audit pass and makes "leak bursts = 0" the headline metric.
3. **"Don't put me in it" requests:** a one-click *remove person* (hide plus optional cut of their segments), with the receipt as proof of compliance.
