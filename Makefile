ifndef PYTHONPATH
	export PYTHONPATH = ../yapps2
endif

ifndef YAPPS
	export YAPPS = ../yapps2/yapps2.py
endif

CRUNNER = scripts/crunner.py

sparrow/compiler/parser.py: sparrow/compiler/parser.g
	$(YAPPS) sparrow/compiler/parser.g

parser: sparrow/compiler/parser.py

all: parser


.PHONY : no_whitespace_tests
no_whitespace_tests: clean_tests parser
	$(CRUNNER) -qo tests/*txt tests/*tmpl
	$(CRUNNER) --test-input tests/input/search_list_data.pye -qt tests/*txt tests/*tmpl
	$(CRUNNER) -O1 -qo tests/*txt tests/*tmpl
	$(CRUNNER) -O1 --test-input tests/input/search_list_data.pye -qt tests/*txt tests/*tmpl

.PHONY : whitespace_tests
whitespace_tests: clean_tests parser
	$(CRUNNER) --preserve-optional-whitespace -qo tests/*txt tests/*tmpl
	$(CRUNNER) --preserve-optional-whitespace --test-input tests/input/search_list_data.pye --test-output output-preserve-whitespace -qt tests/*txt tests/*tmpl
	$(CRUNNER) -O1 --preserve-optional-whitespace -qo tests/*txt tests/*tmpl
	$(CRUNNER) -O1 --preserve-optional-whitespace --test-input tests/input/search_list_data.pye --test-output output-preserve-whitespace -qt tests/*txt tests/*tmpl

.PHONY : tests
tests: no_whitespace_tests whitespace_tests


.PHONY : clean
clean:
	@find . -name '*.pyc' -exec rm {} \;
	@rm -f sparrow/compiler/parser.py
	@rm -rf build

.PHONY : clean_tests
clean_tests:
	@rm -f tests/*.py
	@rm -f tests/*.pyc
	@find tests -name '*.failed' -exec rm {} \;
	@touch tests/__init__.py

.PHONE : clean_all
clean_all : clean clean_tests
