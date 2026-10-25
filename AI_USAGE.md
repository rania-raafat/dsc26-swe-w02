# AI usage

Keep all three headings exactly as they are. If this file is missing or any heading is
missing, the grader stops and gives 0 ("AI_USAGE.md missing or incomplete"). The content
is not scored, but your Track Mentor reads it and the W8 defence can ask about it.

## Tools

I worked on most of the task on my own, but whenever I got stuck or didn't fully understand something, I used ChatGPT to help me figure it out. It helped me understand the parcel state transitions, FastAPI error handling, and cursor pagination. I also asked for help checking some edge cases and coming up with extra tests. I tried the code myself and used the test results to see what needed fixing.
## What AI got wrong

Not every suggestion was ready to use as it was, so I had to compare it with the task requirements and check the code myself. I paid extra attention to the error response format and the OpenAPI documentation to make sure they matched what the task asked for. I made adjustments where needed and ran the tests again.

## In my own words

1. Why does `listParcels` need a cursor rather than an offset?
ans: I used a cursor because parcel states can change while someone is moving through the pages. With offset pagination, this can cause some parcels to be skipped or shown more than once, while a cursor lets us continue from the last parcel we reached.

2. Which of your four operations would break the courier app if you renamed one field, and who would have to approve that change?
ans: Changing a field name could break the courier app or the merchant integration if they still expect the old name. I would discuss the change with the teams using the API, especially the courier app team and the merchant integration team, before changing the contract.
