mkdir temp_merge
cd temp_merge
git clone git@devtools:general/templates.git
cd templates
git checkout $1
template-gen $3 $4 projectfromtemplate $5 $6 $7 $8
cd projectfromtemplate
git init
git add --all
git commit -m "project from first template"
git checkout -b templatebranch
cd ..
git checkout $2
template-gen $3 $4 projectfromtemplate2 $5 $6 $7 $8
cp -r projectfromtemplate2/. projectfromtemplate
cd projectfromtemplate
git add --all
git commit -m "project from updated template"
git checkout main
cd ../../..
cp -r !(.git|temp_merge) temp_merge/templates/projectfromtemplate
cd temp_merge/templates/projectfromtemplate
git add --all
git commit -m "Added code from existing project"
git merge templatebranch -m "Merged changes in template into existing project"
cp -r !(.git) ../../..
cd ../../..
rm -r temp_merge


