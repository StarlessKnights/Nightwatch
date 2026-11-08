# HACKUTD: ZERO DAY 2026
## The Team: Pericynthion
Ryan Nirmal, Maaz Kattangere, Manas Telikepalli, Avi Singa

## Inspiration
Our inspiration was derived from the growing number of service outages that have been on the rise recently stemming from the lack of communication and organization within systems internal to the largest data centers in the world.

One specific example of such an outage was the 2017 British Airways IT outage, in which a supply failure in one of the UK data centers resulted in a widespread disruption of the entire service. Affecting over 75,000 passengers and hundreds of flights, a slipup in data center control caused a consumer-wide service degradation. Incidents like these highlight how a single failure within a data center could translate to devastating consequences in the real world. 
Recognizing this challenge, we set out to build a platform that would allow for data center technicians to minimize human error, forecast future failures, and stay in control of their data centers. 


## What it does
NIGHTWATCH is a fault-tolerant, multi-layered, decision-support tool for the operators of a data center cooling facility. It simulates cooling pump loss, thermal runaway, and cooling tower output constraints. 

NIGHTWATCH is separated into multiple modules: the main node-based graph of the facility, the trends and forecasting of the states of all nodes, the immediate decision engine, and NIGHTWATCH Intelligence which features NVIDIA’s line of Nemotron models to gather sparse data both historical and immediate to form interpretations on best future actions and potential required handoffs. 

The Decision Engine and NIGHTWATCH Intelligence both predict the state of the facility ahead of time to ensure minimal production losses by offering solutions such as diverting cooling lines, slowing down flow through the facility, or reducing our inflow of heat. Each suggestion has a strict time-to-limit and act-by deadline to report to operators the deadlines they have to execute the suggestion before it gets superseded by further faults.

Additionally, NIGHTWATCH allows for facility operators to run “What-If” scenarios to compare the state of a facility in the future based on different initial conditions. For example, if a facility operator wants to understand the risk associated with the degradation of a cooling pump, they can simulate the way the facility will respond and have actions taken to prevent excessive production losses before the pumps even begin to fail.

As a result, when emergencies occur, operators have instant insight into all systems affected as well as tailored suggestions on further actions ultimately to reduce downtime and keep losses low.



## How we built it

## Challenges we ran into
One of the most frustrating (but rewarding!) challenges we ran into was configuring our Arduino R4 microcontrollers to interact with and react to changes made on the web app. Sometimes, the Arduino matrices would not display the correct animations, the computer would not use the correct COM ports, or the web app would not be able to recognize the Arduinos at all. We got around this by implementing an automatic arduino COM port detector and flasher, allowing us to guarantee that we would always have working and reliable connections.


## Accomplishments that we're proud of
Overall, we are incredibly proud of NIGHTWATCH Intelligence as a multi-agent system that runs continuously in the background, constantly evaluating the entire system infrastructure to ensure the data center operates efficiently. The system consists of three agents, each with specific responsibilities, primarily monitoring factors such as temperature, cooling, and workload placement. Each agent iterates through our graph and provides the main agent (the coordinator agent) with a summary of its respective area of the data center, allowing technicians to make more informed decisions. We are particularly proud of this feature because it can operate continuously as a maintenance system for the data center while accurately reporting and citing the sources of any disruptions as they arise.



## What we learned
We learned a lot about industry terms and the types of safety interlocks that systems like these typically have. Terms like load shed and HH protection both serve to protect internal systems from offscale-high values like in the case of thermal runaway. 

Additionally, we experienced a lot of success with our implementation of NIGHTWATCH Intelligence both with our smart decision tree and NVIDIA’s Nemotron lineup. Both offered new, differing perspectives from each other which taught us a lot about the strengths and weaknesses of either solution when it comes to sparse data interpretation.


## What's next for Nightwatch
As of now, the NIGHTWATCH software is entirely simulation based. However, it is based on real industry concepts thus a continuation of this project would involve real integration with on-site sensors to first get telemetry flowing through both our Decision Engine and NIGHTWATCH Intelligence and then tailor solutions towards the facility’s needs to bring the accelerated insights directly to the datacenters that need them most.

