## RAG ARCHITECTURE

                USER QUERY
                    │
                    ▼
           Profanity Detection
                    │
          ┌─────────┴─────────┐
       profanity             clean
          │                    │
          ▼                    ▼
   close request        Query Classification
                               │
                 ┌─────────────┴─────────────┐
                 │                           │
         non-technical                   technical
                 │                           │
                 ▼                           ▼
                L1                          L3
                 │                           │
          answered?                    answered?
          ┌──────┴──────┐              ┌────┴────┐
         yes            no             yes       no
          │              │              │         │
          ▼              ▼              ▼         ▼
       ANSWER           L2           ANSWER    OPERATOR
                         │
                   answered?
                  ┌──────┴──────┐
                 yes            no
                  │              │
                  ▼              ▼
               ANSWER           L3
                                 │
                           answered?
                          ┌──────┴──────┐
                         yes            no
                          │              │
                          ▼              ▼
                       ANSWER         OPERATOR

