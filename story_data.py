#!/usr/bin/env python3
"""
Story and Question Data for Wippi Q&A Agent
Auto-generated from Questions CSV
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
import csv
import os


@dataclass
class Question:
    """A single question for a chapter."""
    question_no: int
    question_text: str
    expected_answers: List[str]  # Multiple acceptable answers
    
    def check_answer(self, user_answer: str) -> bool:
        """Check if user's answer matches any expected answer (case-insensitive, partial match)."""
        user_lower = user_answer.lower().strip()
        # Remove common filler words
        user_clean = user_lower.replace("the ", "").replace("a ", "").replace("an ", "")
        
        for expected in self.expected_answers:
            expected_lower = expected.lower().strip()
            expected_clean = expected_lower.replace("the ", "").replace("a ", "").replace("an ", "")
            
            # Exact match
            if expected_lower == user_lower or expected_clean == user_clean:
                return True
            # Partial match (answer contains expected or vice versa)
            if expected_clean in user_clean or user_clean in expected_clean:
                return True
            # Word match (any word in expected appears in user's answer)
            expected_words = expected_clean.split()
            for word in expected_words:
                if len(word) > 3 and word in user_clean:  # Only check words > 3 chars
                    return True
        return False


@dataclass
class Chapter:
    """A chapter with its questions."""
    chapter_id: str
    chapter_name: str
    summary: str = ""  # Brief summary for AI context
    questions: List[Question] = field(default_factory=list)


@dataclass
class Story:
    """A complete story with all chapters."""
    story_id: str
    story_name: str
    chapters: Dict[str, Chapter] = field(default_factory=dict)
    
    def get_chapter(self, chapter_id: str) -> Optional[Chapter]:
        return self.chapters.get(chapter_id)
    
    def get_chapter_questions(self, chapter_id: str) -> List[Question]:
        chapter = self.get_chapter(chapter_id)
        return chapter.questions if chapter else []
    
    def get_next_chapter_id(self, current_chapter_id: str) -> Optional[str]:
        """Get the next chapter ID after the current one."""
        chapter_ids = list(self.chapters.keys())
        try:
            current_index = chapter_ids.index(current_chapter_id)
            if current_index + 1 < len(chapter_ids):
                return chapter_ids[current_index + 1]
        except ValueError:
            pass
        return None
    
    def is_last_chapter(self, chapter_id: str) -> bool:
        """Check if this is the last chapter."""
        chapter_ids = list(self.chapters.keys())
        return chapter_ids[-1] == chapter_id if chapter_ids else True
    
    def list_chapters(self) -> List[tuple]:
        """List all chapters as (id, name) tuples."""
        return [(ch.chapter_id, ch.chapter_name) for ch in self.chapters.values()]


# ==================== CINDERELLA STORY DATA ====================

CINDERELLA_STORY = Story(
    story_id="cinderella",
    story_name="Cinderella",
    chapters={
        "1": Chapter(
            chapter_id="1",
            chapter_name="Dust and Dishes",
            summary="""Cinderella lives in a house where she does all the work - sweeping floors, scrubbing pots, 
and helping her two stepsisters Olga and Bertha. Her stepmother Madam Gertrude gives orders constantly.
Cinderella's only friends are Pebble the cheeky squirrel and Tuff the fast-talking sparrow. 
Tuff ate a chocolate medal and calls it a victory. Pebble calls himself the 'kitchen hero'.
Despite all the hard work, Cinderella's heart is full of hope. She dreams of one quiet day just for herself.
Her name comes from the cinders and ash she works with.""",
            questions=[
                Question(1, "Kian, who is Cinderella's cheeky squirrel friend?", ["Pebble"]),
                Question(2, "What bird friend talks very fast?", ["Tuff"]),
                Question(3, "What did Tuff eat that was made of chocolate?", ["A medal", "medal", "chocolate medal"]),
                Question(4, "What does Cinderella use to clean the floors?", ["A broom", "broom"]),
                Question(5, "Who is the mean lady giving orders?", ["Madam Gertrude", "Gertrude", "madam"]),
                Question(6, "How many sisters does Cinderella have?", ["Two", "2", "two sisters"]),
                Question(7, "What does Olga have in her messy hair?", ["Bird's nest", "birds nest", "nest", "bird nest"]),
                Question(8, "What is Cinderella's heart full of?", ["Hope"]),
                Question(9, "What does Pebble call himself?", ["Kitchen hero", "hero"]),
                Question(10, "What does Cinderella want one of?", ["Quiet day", "quiet", "peace", "peaceful day"]),
            ]
        ),
        "2": Chapter(
            chapter_id="2",
            chapter_name="The Royal Invitation",
            summary="""A Royal Messenger arrives at the door with a loud trumpet announcing a grand ball at the palace!
Prince Leo is inviting everyone. The letter has a gold seal. Madam Gertrude and the sisters fly down 
the stairs like overstuffed teapots in excitement. Bertha accidentally tries to wear Olga's shoes.
Pebble was counting acorns on the window when the messenger came. The messenger played his trumpet loudly.
Cinderella wishes she could go to the palace too. Pebble and Tuff tell her she has spirit and kindness.
A tiny hope begins to grow in Cinderella's heart - what if she could go to the ball?""",
            questions=[
                Question(1, "Kian, who brought a loud trumpet to the door?", ["Royal Messenger", "messenger", "royal"]),
                Question(2, "What is the fancy palace party called?", ["The Ball", "ball"]),
                Question(3, "What is the name of the kind Prince?", ["Prince Leo", "Leo"]),
                Question(4, "What did the sisters fly down like?", ["Teapots", "teapot"]),
                Question(5, "What did Bertha try to put on?", ["Olga's shoes", "shoes", "Olga shoes"]),
                Question(6, "What was Pebble counting on the window?", ["Acorns", "acorn"]),
                Question(7, "What did the messenger play?", ["A trumpet", "trumpet"]),
                Question(8, "What color was the special letter's seal?", ["Gold", "golden"]),
                Question(9, "Where did Cinderella wish she could go?", ["The Palace", "palace"]),
                Question(10, "What did the birds say Cinderella has?", ["Spirit"]),
            ]
        ),
        "3": Chapter(
            chapter_id="3",
            chapter_name="The Garden and the Wish",
            summary="""After the family leaves for the ball, Cinderella goes to the garden to be alone.
She sits near a big orange pumpkin. The air smells of lavender flowers. Pebble thinks it's like a soap opera!
Tuff was panicking about the whole situation. Cinderella just wants to be seen - not ignored anymore.
Then something magical happens - the Fairy Godmother appears in a silver glow! 
She heard Cinderella's wish. She offers Cinderella stars and asks if she wants to go to the ball.
Cinderella says 'Yes' to the magic, and everything is about to change!""",
            questions=[
                Question(1, "Kian, where did Cinderella go to be alone?", ["The Garden", "garden"]),
                Question(2, "What big orange vegetable was near her?", ["A pumpkin", "pumpkin"]),
                Question(3, "Who appeared in a silver glow?", ["Fairy Godmother", "godmother", "fairy"]),
                Question(4, "What flower did the air smell like?", ["Lavender"]),
                Question(5, "What did the Fairy Godmother hear?", ["A wish", "wish"]),
                Question(6, "What did Cinderella want to be?", ["Seen"]),
                Question(7, "What did the squirrel think this was?", ["Soap opera", "soap", "opera"]),
                Question(8, "Who was panicking in the garden?", ["Tuff"]),
                Question(9, "What did the lady offer Cinderella?", ["Stars", "star"]),
                Question(10, "What did Cinderella say to the magic?", ["Yes"]),
            ]
        ),
        "4": Chapter(
            chapter_id="4",
            chapter_name="The Ball",
            summary="""The Fairy Godmother works her magic! The pumpkin turns into a shining carriage.
The little mice become beautiful horses. A sleepy lizard becomes the driver with a top hat!
Cinderella gets a sky blue dress and glass slippers made of clear glass, strong as hope.
But the magic stops at midnight - when the clock strikes twelve, everything turns back!
At the ball, Prince Leo finds Cinderella. They dance and talk on the balcony.
But the clock strikes midnight! Cinderella runs away, leaving one glass slipper on the stairs.""",
            questions=[
                Question(1, "Kian, what did the pumpkin turn into?", ["A carriage", "carriage"]),
                Question(2, "What did the little mice become?", ["Horses", "horse"]),
                Question(3, "What animal became the driver?", ["A lizard", "lizard"]),
                Question(4, "What were Cinderella's shoes made of?", ["Glass"]),
                Question(5, "What time does the magic stop?", ["Midnight", "12", "twelve"]),
                Question(6, "Who did Cinderella dance with?", ["Prince Leo", "Leo", "prince", "the prince"]),
                Question(7, "Where did they go for a quiet talk?", ["The balcony", "balcony"]),
                Question(8, "What did Cinderella leave on the stairs?", ["One slipper", "slipper", "shoe", "glass slipper"]),
                Question(9, "What color was her dress?", ["Sky blue", "blue"]),
                Question(10, "How did she leave the party?", ["Running", "run", "ran"]),
            ]
        ),
        "5": Chapter(
            chapter_id="5",
            chapter_name="Whispers and Wonders",
            summary="""The next morning, Cinderella is back in the kitchen with flour on her hands, keeping her secret.
The ball is her secret! Pebble and Tuff do a funny reenactment - Pebble pretends to be a chandelier!
The stepsisters talk about the mystery girl at the ball. Bertha tripped at the party!
Tuff ate a napkin at the table. The Prince is looking for the mystery girl.
The sisters want to copy her style. Prince Leo looked at Cinderella like he actually saw her.
In the garden, Cinderella touches a rose and knows she was the beginning of a story.""",
            questions=[
                Question(1, "Kian, what secret did Cinderella have?", ["The ball", "ball"]),
                Question(2, "What did Pebble pretend to be?", ["A chandelier", "chandelier"]),
                Question(3, "Who tripped at the big party?", ["Bertha"]),
                Question(4, "What was on Cinderella's hands in the morning?", ["Flour"]),
                Question(5, "Who is the Prince looking for?", ["Mystery girl", "mystery", "girl"]),
                Question(6, "What did the sisters want to copy?", ["Her style", "style"]),
                Question(7, "What did Tuff eat at the table?", ["A napkin", "napkin"]),
                Question(8, "How did Prince Leo look at her?", ["He saw her", "saw her", "he saw"]),
                Question(9, "What did Cinderella touch in the garden?", ["A rose", "rose"]),
                Question(10, "What was Cinderella the beginning of?", ["A story", "story"]),
            ]
        ),
        "6": Chapter(
            chapter_id="6",
            chapter_name="Before the Knock",
            summary="""The Prince is coming with the glass slipper wrapped in velvet! He's searching for the mystery girl.
Tuff heard a knock at the door - but it was just a bird at first. They even tried the shoe on a goat!
Even the teapot looked nervous. An old woman tells Cinderella she has a secret and is glowing.
Tuff (the sparrow) says Cinderella has layers - she's more than just a kitchen maid.
Cinderella waits in the kitchen, scared of being seen but also hoping to be found.
Something is about to happen at the door - a knock. The Prince is coming to the house!""",
            questions=[
                Question(1, "Kian, what is the Prince carrying in velvet?", ["Glass slipper", "slipper", "shoe"]),
                Question(2, "Who heard a bird knock on the door?", ["Tuff"]),
                Question(3, "What animal did they try the shoe on?", ["A goat", "goat"]),
                Question(4, "Who looked very nervous like a teapot?", ["The teapot", "teapot"]),
                Question(5, "What did the old woman say Cinderella has?", ["A secret", "secret"]),
                Question(6, "What is the sparrow's name?", ["Tuff"]),
                Question(7, "Where was Cinderella waiting?", ["The kitchen", "kitchen"]),
                Question(8, "What does Tuff say Cinderella has?", ["Layers", "layer"]),
                Question(9, "What was about to happen at the door?", ["A knock", "knock"]),
                Question(10, "Who is coming to the house?", ["The Prince", "prince", "Prince Leo", "Leo"]),
            ]
        ),
        "7": Chapter(
            chapter_id="7",
            chapter_name="The Slipper Fits",
            summary="""The glass slipper arrives! Olga tries first - she even puts butter on her toes to make it fit!
Bertha's foot turns blue from squeezing so hard! Madam Gertrude even makes a fake shoe from cardboard!
Sir Hector Grey says 'toe magic is not an accredited field' when Gertrude claims tricks.
Then Cinderella steps out of the kitchen. She tries the slipper - and it fits perfectly!
The curtains applauded! Tuff wants to eat pudding to celebrate. Prince Leo knew it was her all along.
They walk outside together. Cinderella finally asks to be seen, and she is!""",
            questions=[
                Question(1, "Kian, what did Olga put on her toes?", ["Butter"]),
                Question(2, "What color did Bertha's foot turn?", ["A blue shade", "blue"]),
                Question(3, "What was the fake shoe made of?", ["Cardboard"]),
                Question(4, "Who stepped out of the kitchen?", ["Cinderella"]),
                Question(5, "What did the curtains do?", ["Applauded", "clapped", "applaud"]),
                Question(6, "What does Tuff want to eat now?", ["Pudding"]),
                Question(7, "Who tried the shoe last?", ["Cinderella"]),
                Question(8, "What field did the advisor say isn't real?", ["Toe magic", "toe"]),
                Question(9, "Who knew it was her?", ["Prince Leo", "Leo", "prince", "the prince"]),
                Question(10, "Where did they walk together?", ["Outside"]),
            ]
        ),
        "8": Chapter(
            chapter_id="8",
            chapter_name="The Proposal & The Party",
            summary="""Prince Leo proposes to Cinderella in the garden! She says yes! The whole kingdom celebrates.
There's a special wedding cake made of acorns (for Pebble!). A little boy gives Cinderella a crooked wooden spoon.
Queen Elena adjusts Cinderella's veil with kindness. Pebble wears a tiny sash made of royal napkin!
The mice wear tiny hats on their heads. King Bramble keeps asking where the cheese is!
Prince Leo and Cinderella promise to choose each other every day. Children chase fireflies at the party.
To Prince Leo, Cinderella looks like hope. And for them both, a new chapter is starting!""",
            questions=[
                Question(1, "Kian, what was the special cake made of?", ["Acorns", "acorn"]),
                Question(2, "What did the little boy give Cinderella?", ["A spoon", "spoon"]),
                Question(3, "Who adjusted Cinderella's veil?", ["Queen Elena", "Elena", "queen"]),
                Question(4, "What did Pebble wear to the wedding?", ["A sash", "sash"]),
                Question(5, "What did the mice wear on their heads?", ["Tiny hats", "hats", "hat"]),
                Question(6, "What did they promise to do every day?", ["Choose"]),
                Question(7, "What did the children chase?", ["Fireflies", "firefly"]),
                Question(8, "What did King Bramble want to find?", ["Cheese"]),
                Question(9, "How did Cinderella look to the Prince?", ["Like hope", "hope"]),
                Question(10, "What was starting for them?", ["New chapter", "chapter", "new"]),
            ]
        ),
    }
)


# ==================== STORY REGISTRY ====================

STORIES: Dict[str, Story] = {
    "cinderella": CINDERELLA_STORY,
}


def get_story(story_id: str) -> Optional[Story]:
    """Get a story by ID."""
    return STORIES.get(story_id.lower())


def list_stories() -> List[str]:
    """List all available story IDs."""
    return list(STORIES.keys())


def load_story_from_csv(csv_path: str, story_id: str, story_name: str) -> Story:
    """
    Load story questions from CSV file.
    Expected format: ,Chapter Id,Question No,Question Text,Expected Answers
    """
    story = Story(story_id=story_id, story_name=story_name)
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader)  # Skip empty row
        next(reader)  # Skip header row
        
        for row in reader:
            if len(row) < 5:
                continue
            
            chapter_id_name = row[1].strip()
            question_no = row[2].strip()
            question_text = row[3].strip()
            expected_answer = row[4].strip()
            
            if not chapter_id_name or not question_text:
                continue
            
            # Parse chapter ID and name (format: "1: Chapter Name")
            if ':' in chapter_id_name:
                chapter_id, chapter_name = chapter_id_name.split(':', 1)
                chapter_id = chapter_id.strip()
                chapter_name = chapter_name.strip()
            else:
                chapter_id = chapter_id_name
                chapter_name = chapter_id_name
            
            # Create chapter if doesn't exist
            if chapter_id not in story.chapters:
                story.chapters[chapter_id] = Chapter(
                    chapter_id=chapter_id,
                    chapter_name=chapter_name
                )
            
            # Clean question text (remove trailing numbers)
            clean_question = question_text.rstrip('0123456789 ')
            
            # Parse question number
            try:
                q_no = int(question_no)
            except ValueError:
                q_no = len(story.chapters[chapter_id].questions) + 1
            
            # Add question
            story.chapters[chapter_id].questions.append(
                Question(
                    question_no=q_no,
                    question_text=clean_question,
                    expected_answers=[expected_answer]
                )
            )
    
    return story


# ==================== Q&A SESSION STATE ====================

@dataclass
class QASession:
    """Tracks Q&A session state for a user."""
    session_id: str
    story_id: str
    current_chapter_id: str
    current_question_index: int = 0
    score: int = 0
    total_questions: int = 0
    answers: List[Dict] = field(default_factory=list)
    is_complete: bool = False
    
    def get_current_question(self, story: Story) -> Optional[Question]:
        """Get the current question."""
        questions = story.get_chapter_questions(self.current_chapter_id)
        if self.current_question_index < len(questions):
            return questions[self.current_question_index]
        return None
    
    def record_answer(self, question: Question, user_answer: str, is_correct: bool):
        """Record an answer."""
        self.answers.append({
            "chapter_id": self.current_chapter_id,
            "question_no": question.question_no,
            "question": question.question_text,
            "user_answer": user_answer,
            "correct": is_correct,
            "expected": question.expected_answers[0]
        })
        self.total_questions += 1
        if is_correct:
            self.score += 1
        self.current_question_index += 1
    
    def is_chapter_complete(self, story: Story) -> bool:
        """Check if all questions for current chapter are done."""
        questions = story.get_chapter_questions(self.current_chapter_id)
        return self.current_question_index >= len(questions)
    
    def move_to_next_chapter(self, story: Story) -> bool:
        """Move to next chapter. Returns False if story is complete."""
        next_chapter = story.get_next_chapter_id(self.current_chapter_id)
        if next_chapter:
            self.current_chapter_id = next_chapter
            self.current_question_index = 0
            return True
        else:
            self.is_complete = True
            return False
    
    def get_score_summary(self) -> str:
        """Get a summary of the score."""
        percentage = (self.score / self.total_questions * 100) if self.total_questions > 0 else 0
        return f"{self.score} out of {self.total_questions} ({percentage:.0f}%)"
    
    def get_praise_message(self) -> str:
        """Get appropriate praise based on score."""
        if self.total_questions == 0:
            return "Great listening!"
        
        percentage = self.score / self.total_questions * 100
        
        if percentage >= 90:
            return "WOW! You are absolutely AMAZING! You got almost everything right! You're a superstar listener!"
        elif percentage >= 70:
            return "Great job! You remembered so many things from the story! You're such a good listener!"
        elif percentage >= 50:
            return "Good effort! You remembered many parts of the story. Keep listening and you'll get even better!"
        else:
            return "Nice try! Every story teaches us something new. You did your best and that's what matters!"
