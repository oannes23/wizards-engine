# UI Cleanup

The purpose of this document is to list improvements we can make to the UI. When the time comes to implement this and turn it into epics and stories, you should examine everything in this list, look for common patterns, and fix them on the highest level of abstraction within the code base that you can in order to solve the underlying UX flow issue and not just the singular instance of a pattern. Make sure that any changes are made are incorporated into future UX design principles. When you make epics and stories, also consider adding additional ones that might improve the flow on top of the specific changes suggested here. You should even feel free to rethink the way entire sections are presented if you believe it may lead to a superior experience for the user.

Also please note these UI impressions are based on the desktop view, not mobile. Feel free to modify mobile as well to match as best you can.

## GM View
When it first loads in, I see the Feed, but no top menu bar. If I click on "All" in the Feed, the top menu bar does appear, but it should appear on load.

For the top tabs, Queue is good. Others should be Event Feed (All Events, filterable in a modern UI table design with lots of good useful information summarizing each event so the GM can scroll quickly down the list, sort, filter, etc), Game Objects (replacing the World tab, with similar good sortable high info table maybe made of slightly larger wide horizontal cards as rows kinda like the Stories part of the current World tab, still sortable and filterable etc), Sessions is good though we should clean up the design and view and make it more modern similar to the others, More currently doesn't seem to do anything with the test sample data.

Here is some more specific information.

### Queue Tab
The PC meters displayed are all out of 5 rather than the actual resource maximums of each resource.

We should make the list of PCs more compact, or we should expand each listing to be more informative. Maybe also include a list of any Traits or Bonds low on charges (2 or fewer remaining). Try to do both, make it more compact (maybe even 3 columns of PCs?) and more useful (each PC card has a bit more than the meters, and the meters are much less wide so the card is 1/3 screen real estate). Also maybe include at the bottom of each card the most recent 3 events associated with the PC, "No Events found" if none yet for this group.

We should also include a list of Groups at the bottom, sorted by who is actually doing stuff at the top so we can see things happening. For these groups show any projects they're on and maybe 3 most recent events, "No Events found" if none yet for this group.

### Feed Tab
Each feed entry is not very informative. I would expect to see a table showing name, source (is this an event? an entry in a story? a proposal received?), every single change in any state in the world, every proposal, every bit of information a GM cares about should be in this feed with different top category filters available to change what I can see.

Clicking on any item in the Feed should bring me to the detail view of that thng (GameObject, Event, Player, etc) with different parts of the feed row entry linking to different things instead of just the thing itself if it makes sense, like maybe list parent, target, yadda yadda yadda

### World Tab
Each entry's description is hard to read, with the black background and gray text. It's more legible on mouseover but we should make it easier to read. We should also have a different tab for PCs vs NPCs instead of the little tag on each entry.

The Search By Name is good, but should be smaller and alongside a lot more standardized table UX elements like filtering by various columns, sorting, etc.

In general every Game Object view should also have a CRUD page to create a new one, edit an existing one, or delete (soft delete archive) an old one.

#### NPC Character Detail View
If the NPC has a Bond to a PC, both the NPC's Bond to the PC and the PC's Bond to the NPC appear in the NPC's Bond list. We only need to see the NPC's Bond to the PC. The abstract narrative Bond is the dyad that connects them, but each has it represented by their own Bond Trait held by each member of the dyad.

#### PC Character Detail View
The Description shouldn't be truncated. Skills should be shown immediately after the Description, in a compacted table. I only see "Traits", not Core Traits and Role Traits both. Each Trait display should have the Name and Charges, and if you click on it, it can expand to show the description, clicking it again collapses. It should have a button that when clicked takes you to the edit page for that particular Trait. 

The Bonds section should work similarly, showing each Bond name and Charges, and clicking to expand shows description. The expanded Description also has a button to go to the Game Object that is the other side of the Bond dyad. It should also have a button to the edit page. 

The Bonds also have the same "showing both sides of the dyad instead of the just the side connected to this Game Object" problem as NPCs.

The Full Sheet button kinda doesn't do anything.

At the very bottom should be the Events Feed for that particular player Game Object and everything they can see based on their Bonds.





