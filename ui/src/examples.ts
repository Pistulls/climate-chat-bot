// Sample comments for the "See some examples" picker. Invented for testing, like the
// eval set they come from (eval/replies.toml); none are copied from real people.

export const EXAMPLES: string[] = [
    "Last time I checked solar panels don't work at night so we need gas to keep the lights on",
    "There has been no global warming since 1998. Look at the satellite data.",
    "lol the sea isn't rising any faster than it did 100 yrs ago, alarmists making stuff up again",
    "CO2 has always gone up and down naturally. Humans are a tiny fraction of it.",
    "More CO2 is good for plants. Greening planet. Warmer is better than colder anyway.",
    "Wind turbines are useless, they don't turn half the time and cost a fortune",
    "The climate models have been wrong for 30 years. Why would anyone trust them now?",
    "Global warming is misinformation, it's just weather!",
    "Global warming isn't man made, it's the natural heating and cooling cycle of the earth over millions of years",
    "Renewables are responsible for higher cost of energy",
    "Clean coal is emits far less emissions than it takes to build solar panels and wind turbines",
    "Electric vehicle batteries only last a few years then become toxic in land fills",
    "The cobalt mined to make your electric car battery is far worse for the environment than oil and gas"
];

/** One example at random: the comment box's starting text. */
export function randomExample(random: () => number = Math.random): string {
  return EXAMPLES[Math.floor(random() * EXAMPLES.length)];
}
