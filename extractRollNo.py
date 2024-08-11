import re

def extract_unique_roll_numbers(input_file, output_file):
  """Extracts unique 10-digit roll numbers from an input file and writes them to an output file.

  Args:
    input_file: Path to the input file.
    output_file: Path to the output file.
  """

  roll_numbers = set()  # Use a set to ensure uniqueness

  with open(input_file, 'r') as f:
    text = f.read()

  matches = re.findall(r'\d{10}', text)

  for number in matches:
    roll_numbers.add(number)

  with open(output_file, 'w') as f:
    for number in roll_numbers:
      f.write(number + '\n')

if __name__ == '__main__':
  input_file = 'data/raw_roll_numbers.txt'
  output_file = 'data/roll_numbers.txt'
  extract_unique_roll_numbers(input_file, output_file)
