
import os
import json
import re
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate
from langchain_core.exceptions import OutputParserException

load_dotenv()

def normalize_token(t: str) -> str:
    """
    Standardizes tech terms. 
    e.g. "React.js" -> "react" (matches "React" in portfolio)
    """
    t = str(t).lower().strip()
    t = t.replace('.', '') 
    t = re.sub(r'js$', '', t) 
    t = re.sub(r'[^a-z0-9 +#]', '', t)
    return " ".join(t.split())

class Chain:
    def __init__(self):
        # Llama-3.3-70b-Versatile
        self.llm = ChatGroq(
            temperature=0.0, 
            groq_api_key=os.getenv("GROQ_API_KEY"), 
            model_name="llama-3.3-70b-versatile"
        )

    def clean_json_output(self, content):
        content = str(content)
        if "```" in content:
            content = content.replace("```json", "").replace("```", "")
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
        return content.strip()

    def analyze_job(self, cleaned_text):
        """
        Consolidated function: Extracts Job Details, Skills, and Visa Analysis in ONE pass.
        This saves ~66% of input tokens compared to separate calls.
        """
        prompt_extract = PromptTemplate.from_template(
            """
            ### SCRAPED TEXT FROM WEBSITE:
            {page_data}

            ### INSTRUCTION:
            You are an expert technical recruiter. Extract job details, technical requirements, and legal restrictions.
            
            1. **Job Details**: Extract role, company, location, experience level, and a detailed description.
            2. **Skills**: Identify ALL technical skills, tools, and methodologies (Languages, Cloud, DevOps, Agile, etc.).
            3. **Work Authorization (CRITICAL)**: specific search for:
               - "U.S. Person" / "Citizen Only" / "Security Clearance"
               - "Green Card" / "Permanent Resident"
               - "No Sponsorship" / "No H1B" / "No CPT/OPT"

            ### OUTPUT FORMAT (STRICT JSON ONLY):
            {{
                "role": "Job Title",
                "company": "Company Name",
                "location": "City, State",
                "experience": "Junior/Senior/Years",
                "description": "Detailed summary...",
                "required_skills": ["Python", "React", "AWS", "Agile", "Git", "Docker"],
                "visa_analysis": {{
                    "green_card_only": boolean,
                    "us_citizen_only": boolean,
                    "no_h1b": boolean,
                    "no_opt_cpt": boolean,
                    "security_clearance": boolean,
                    "analysis": "Quote the specific restriction found or 'No restrictions detected'"
                }}
            }}
            """
        )
        chain_extract = prompt_extract | self.llm
        res = chain_extract.invoke(input={"page_data": cleaned_text})
        
        clean_content = self.clean_json_output(res.content)
        
        try:
            parsed = json.loads(clean_content)
        except json.JSONDecodeError:
            try:
                # Fallback extraction logic
                start = clean_content.find('{')
                end = clean_content.rfind('}') + 1
                parsed = json.loads(clean_content[start:end])
            except Exception:
                raise OutputParserException("Unable to parse job analysis")
        
        # Normalize skills immediately for the portfolio matcher
        raw_skills = parsed.get("required_skills", [])
        parsed["normalized_required_skills"] = [normalize_token(s) for s in list(set(raw_skills))]
        
        return parsed

    def write_mail(self, job, links, matched_skills):
        prompt_email = PromptTemplate.from_template(
            """
            ### JOB DESCRIPTION:
            {job_description}

            ### CANDIDATE'S MATCHING SKILLS:
            {matched_skills}

            ### CANDIDATE'S PORTFOLIO LINKS:
            {link_list}

            ### INSTRUCTION:
            You are Jemil Dharia, a Master’s student in Computer Science at Arizona State University.
            Write a cold email to the hiring manager.
            
            Guidelines:
            1. Keep it professional but concise.
            2. Mention the company name if available.
            3. Connect your {matched_skills} to their requirements.
            4. Do not include a subject line in the body.
            """
        )
        
        chain_email = prompt_email | self.llm
        res = chain_email.invoke({
            "job_description": json.dumps(job), # Pass the whole job object for context
            "link_list": links,
            "matched_skills": ", ".join(matched_skills)
        })
        
        return self.clean_json_output(res.content)