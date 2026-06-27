// Shared curated list of internship designations used across HR views.
// Used as a `<datalist>` (Certificate + Offer Letter) so HR gets dropdown
// suggestions while still being able to type any custom value. Strict
// `<select>` views (Offer Letter Email, Offer of Appointment) maintain
// their own constants because their downstream business logic (Annexure
// tier mapping) depends on a closed set.
export const DESIGNATIONS = [
  "AI Research Intern",
  "AI Research Analyst",
  "AI Intern",
  "Machine Learning Intern",
  "Data Science Intern",
  "Data Engineering Intern",
  "Software Engineering Intern",
  "Backend Developer Intern",
  "Frontend Developer Intern",
  "Full Stack Developer Intern",
  "Mobile App Developer Intern",
  "DevOps Intern",
  "Cloud Engineering Intern",
  "Cybersecurity Intern",
  "QA Engineer Intern",
  "UI/UX Design Intern",
  "Product Management Intern",
  "Business Analyst Intern",
  "Marketing Intern",
  "HR Intern",
  "Research Intern",
];
