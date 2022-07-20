Introduction
============

ESI is the official API of EVE Online. You might have heard and used some legendary third-party apps, such as 
`zKillboard <https://zkillboard.com/>`_, 
`SeAT <https://github.com/eveseat/seat>`_, 
`Pyfa <https://github.com/pyfa-org/Pyfa>`_, 
`dotlan <https://evemaps.dotlan.net/>`_, 
`EVE Marketer <https://evemarketer.com/>`_, the list goes on. 
All of them use ESI to retrieve and analyze in-game data in some way, and the outsome is so powerful that we use them all days. 

ESI provides us with in-game data. Everything you can see and read in game is probably accessible with ESI. Things like Jita market, NPC station info, are all available at ESI.
The game client helps you retrieve these data more easily, with just a few clicks in-game, but it can be slow and tiring when you try to, e.g. find which product gives you the most profit when hauling. 
Instead, you can use some programming to automate lots of data collecting, and eventually produce your own third-party application. 

ESI simplifies lots of things between clients (us) and EVE data servers. All we need is to visit a url that defines api endpoints and some parameters, and data will come out in response.
It is similar to visiting any website, like google or facebook, instead the response is useful in-game data. It can be a little troublesome with authenticated request, 
but EVE Tools wraps up authentications, so all you need is to follow some instructions, giving some info, and data come out.

.. note::
    * In chapter 2, basic knowledge of endpoints is discussed.

EVE puts all useful information of ESI at `esi.evetech.net/ui/ <https://esi.evetech.net/ui/>`_. Whenever you feel confused about an endpoint, or want to find an endpoint to suit your needs, 
this is the best place to start with. Usually, google won't tell you much about these endpoints because there aren't many people talking about them. 


