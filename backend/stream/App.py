import streamlit as st
from bokeh.models import Button
from bokeh.models import CustomJS
from streamlit_bokeh_events import streamlit_bokeh_events

def main():
    st.title("Pocket TTS")
    st.write("click the button to convert text to speech")
    stt_button = Button(label="speak", width=100,  button_type="success")
    st.bokeh_chart(stt_button)
    stt_button.js_on_event("button_click", CustomJS(code="""
                                                    var recognition = new webkitSpeechRecognition();
                                                    recognition.continuous = true;
                                                    recognition.interimResults = true;

                                                    recognition.onresult = function (e) {
                                                        var value = "";
                                                        for (var i = e.resultIndex; i < e.results.length; ++i) {
                                                            if (e.results[i].isFinal) {
                                                                value += e.results[i][0].transcript;
                                                            }
                                                        }
                                                        if (value != "") {
                                                            document.dispatchEvent(new CustomEvent("GET_TEXT", {detail: value}));
                                                        }
                                                    }
                                                    recognition.start();
                                                    """))
    result = streamlit_bokeh_events(
        stt_button,
        events="GET_TEXT",
        key="listen",
        refresh_on_update=False,
        override_height=75,
        debounce_time=0
    )
    if result:
        if "GET_TEXT" in result:
            st.write(result.get("GET_TEXT"))
    

if __name__ == "__main__":
    main()